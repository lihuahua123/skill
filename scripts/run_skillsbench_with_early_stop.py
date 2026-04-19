#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from early_stop_policy import (
    EARLY_STOP_STRATEGY_HEURISTIC,
    EARLY_STOP_STRATEGY_PAPER_DYNAMIC_TURN,
    PaperDynamicTurnConfig,
    TASK_POLICY_AGGRESSIVE,
    TASK_POLICY_CONSERVATIVE,
    TASK_POLICY_DRIFT_ONLY,
    TaskStaticInfo,
    decide_paper_dynamic_turn,
    load_historical_tasks,
    recommend_intra_attempt_mode,
    validate_paper_dynamic_turn_config,
)


PLAN_MARKER_RE = re.compile(
    r"\b(plan:|need to|let me|next i|now i need|i need to|all required|created successfully|"
    r"deliverables have been created|verify the final outputs)\b",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run SkillsBench Harbor job with best-effort intra-attempt early stopping."
    )
    parser.add_argument("--skillsbench-root", required=True, type=Path)
    parser.add_argument("--jobs-root", required=True, type=Path)
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--task-name", required=True, help="Single SkillsBench task name")
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument(
        "--early-stop-strategy",
        choices=(EARLY_STOP_STRATEGY_HEURISTIC, EARLY_STOP_STRATEGY_PAPER_DYNAMIC_TURN),
        default=EARLY_STOP_STRATEGY_HEURISTIC,
    )
    parser.add_argument("--max-agent-steps", type=int, default=int(os.environ.get("SKILLSBENCH_EARLY_STOP_MAX_AGENT_STEPS", "28")))
    parser.add_argument("--max-minutes-without-verifier", type=float, default=float(os.environ.get("SKILLSBENCH_EARLY_STOP_MAX_MINUTES_WITHOUT_VERIFIER", "15")))
    parser.add_argument("--recent-window", type=int, default=int(os.environ.get("SKILLSBENCH_EARLY_STOP_RECENT_WINDOW", "8")))
    parser.add_argument("--recent-plan-ratio", type=float, default=float(os.environ.get("SKILLSBENCH_EARLY_STOP_RECENT_PLAN_RATIO", "0.75")))
    parser.add_argument(
        "--paper-initial-turn-limit",
        type=int,
        default=int(os.environ.get("SKILLSBENCH_PAPER_DYNAMIC_TURN_INITIAL", "14")),
    )
    parser.add_argument(
        "--paper-extension-turn-limit",
        type=int,
        default=int(os.environ.get("SKILLSBENCH_PAPER_DYNAMIC_TURN_EXTENSION", "14")),
    )
    parser.add_argument("--grace-seconds", type=float, default=20.0)
    parser.add_argument(
        "--historical-tasks-path",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "analysis" / "rq1" / "aggregated_results.json",
    )
    parser.add_argument("harbor_args", nargs=argparse.REMAINDER)
    return parser.parse_args()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _iso_to_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _load_steps(trial_dir: Path) -> list[dict[str, Any]]:
    payload = _read_json(trial_dir / "agent" / "trajectory.json")
    if not isinstance(payload, dict):
        return []
    steps = payload.get("steps")
    if not isinstance(steps, list):
        return []
    return [s for s in steps if isinstance(s, dict)]


def _trajectory_metrics(trial_dir: Path) -> dict[str, int]:
    payload = _read_json(trial_dir / "agent" / "trajectory.json")
    if not isinstance(payload, dict):
        return {}
    metrics = payload.get("final_metrics")
    if not isinstance(metrics, dict):
        return {}
    return {
        "prompt_tokens": int(metrics.get("total_prompt_tokens") or 0),
        "completion_tokens": int(metrics.get("total_completion_tokens") or 0),
        "cache_tokens": int(metrics.get("total_cached_tokens") or 0),
    }


def _recent_plan_ratio(agent_messages: list[str], recent_window: int) -> float:
    if not agent_messages:
        return 0.0
    recent = agent_messages[-recent_window:]
    if not recent:
        return 0.0
    hits = sum(1 for msg in recent if PLAN_MARKER_RE.search(msg or ""))
    return hits / len(recent)


def _verifier_started(trial_dir: Path) -> bool:
    verifier = trial_dir / "verifier"
    if not verifier.exists():
        return False
    for name in ("reward.txt", "reward.json", "ctrf.json", "test-stdout.txt", "test-stderr.txt"):
        if (verifier / name).exists():
            return True
    return False


def _load_trial_config(trial_dir: Path) -> dict[str, Any]:
    payload = _read_json(trial_dir / "config.json")
    return payload if isinstance(payload, dict) else {}


def _task_environment_dir_from_trial(trial_dir: Path) -> Path | None:
    config = _load_trial_config(trial_dir)
    task_cfg = config.get("task")
    if not isinstance(task_cfg, dict):
        return None
    task_path = task_cfg.get("path")
    if not task_path:
        return None
    return Path(str(task_path)) / "environment"


def _compose_project_name(trial_dir: Path) -> str:
    return trial_dir.name.lower()


def _infer_repo_candidates_from_dockerfile(task_env_dir: Path | None) -> list[str]:
    if task_env_dir is None:
        return ["/app", "/app/workspace", "/workspace", "/root", "/root/workspace", "/home/travis", "/home/github/build"]
    dockerfile = task_env_dir / "Dockerfile"
    if not dockerfile.exists():
        return ["/app", "/app/workspace", "/workspace", "/root", "/root/workspace", "/home/travis", "/home/github/build"]

    candidates: list[str] = []
    for raw_line in dockerfile.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.upper().startswith("WORKDIR "):
            continue
        value = line.split(None, 1)[1].strip()
        if value and "$" not in value and value not in candidates:
            candidates.append(value)

    defaults = ["/app", "/app/workspace", "/workspace", "/root", "/root/workspace", "/home/travis", "/home/github/build"]
    for value in defaults:
        if value not in candidates:
            candidates.append(value)
    return candidates


def _build_patch_probe_script(repo_candidates: list[str]) -> str:
    quoted = " ".join(json.dumps(path) for path in repo_candidates)
    return f"""
set -eu
for repo in {quoted}; do
  if [ ! -d "$repo/.git" ]; then
    continue
  fi
  if ! git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    continue
  fi
  if [ -n "$(git -C "$repo" status --porcelain --untracked-files=all -- . ':(exclude).codex/**' ':(exclude).claude/**' ':(exclude).cache/**' ':(exclude).config/**' ':(exclude).local/**' ':(exclude).npm/**' ':(exclude).cargo/**' ':(exclude).rustup/**' ':(exclude).bash_history' ':(exclude).zsh_history')" ]; then
    echo "$repo"
    exit 0
  fi
done
exit 1
""".strip()


def _workspace_has_non_empty_patch(trial_dir: Path) -> bool | None:
    task_env_dir = _task_environment_dir_from_trial(trial_dir)
    if task_env_dir is None:
        return None

    repo_candidates = _infer_repo_candidates_from_dockerfile(task_env_dir)
    if not repo_candidates:
        return None

    project_name = _compose_project_name(trial_dir)
    ps_cmd = [
        "docker",
        "ps",
        "--filter",
        f"label=com.docker.compose.project={project_name}",
        "--filter",
        "label=com.docker.compose.service=main",
        "--format",
        "{{.ID}}",
    ]
    ps_proc = subprocess.run(ps_cmd, capture_output=True, text=True, check=False)
    if ps_proc.returncode != 0:
        return None
    container_id = (ps_proc.stdout or "").strip().splitlines()
    if not container_id:
        return None

    exec_cmd = [
        "docker",
        "exec",
        container_id[0],
        "bash",
        "-lc",
        _build_patch_probe_script(repo_candidates),
    ]
    exec_proc = subprocess.run(exec_cmd, capture_output=True, text=True, check=False)
    if exec_proc.returncode == 0:
        return bool((exec_proc.stdout or "").strip())
    if exec_proc.returncode == 1:
        return False
    return None


def _load_intra_attempt_context(args: argparse.Namespace) -> dict[str, Any]:
    historical_tasks: list[dict[str, Any]] = []
    if args.historical_tasks_path.exists():
        try:
            historical_tasks = load_historical_tasks(args.historical_tasks_path)
        except Exception:
            historical_tasks = []

    task_info = TaskStaticInfo(task_id=args.task_name)
    recommendation = recommend_intra_attempt_mode(task_info, historical_tasks, top_k=5)
    paper_config = validate_paper_dynamic_turn_config(
        args.paper_initial_turn_limit,
        args.paper_extension_turn_limit,
    )
    return {
        "task_info": task_info,
        "historical_tasks": historical_tasks,
        "recommendation": recommendation,
        "policy": recommendation["policy"],
        "strategy": args.early_stop_strategy,
        "paper_config": paper_config,
    }


def should_early_stop_for_steps(
    steps: list[dict[str, Any]],
    args: argparse.Namespace,
    intra_context: dict[str, Any],
    *,
    current_ts: float | None = None,
    verifier_started: bool = False,
    patch_detected: bool | None = False,
) -> tuple[bool, str | None]:
    if verifier_started:
        return False, None
    if not steps:
        return False, None

    agent_steps = [s for s in steps if s.get("source") == "agent"]
    strategy = intra_context.get("strategy", EARLY_STOP_STRATEGY_HEURISTIC)

    if strategy == EARLY_STOP_STRATEGY_PAPER_DYNAMIC_TURN:
        paper_config = intra_context.get("paper_config")
        if not isinstance(paper_config, PaperDynamicTurnConfig):
            raise ValueError("paper dynamic-turn strategy requires PaperDynamicTurnConfig")
        if patch_detected is None:
            return False, None
        decision = decide_paper_dynamic_turn(
            len(agent_steps),
            patch_detected=bool(patch_detected),
            config=paper_config,
        )
        if decision.should_stop:
            return True, decision.reason
        return False, None

    if len(agent_steps) < max(4, min(args.max_agent_steps, args.recent_window)):
        return False, None

    first_ts = _iso_to_ts(agent_steps[0].get("timestamp"))
    runtime_minutes = 0.0
    if first_ts is not None and current_ts is not None:
        runtime_minutes = max(0.0, current_ts - first_ts) / 60.0

    agent_messages = [str(s.get("message") or "") for s in agent_steps]
    recent_ratio = _recent_plan_ratio(agent_messages, args.recent_window)
    policy = intra_context["policy"]

    if policy == TASK_POLICY_DRIFT_ONLY:
        return False, None

    if policy == TASK_POLICY_CONSERVATIVE:
        return False, None

    if (
        len(agent_steps) >= args.max_agent_steps
        and runtime_minutes >= args.max_minutes_without_verifier
        and recent_ratio >= args.recent_plan_ratio
    ):
        return True, (
            f"intra-attempt early stop: {len(agent_steps)} agent steps, "
            f"{runtime_minutes:.1f}m without verifier, recent plan ratio {recent_ratio:.2f}"
        )

    return False, None


def _build_synthetic_result(trial_dir: Path, reason: str) -> dict[str, Any]:
    config = _read_json(trial_dir / "config.json") or {}
    task_cfg = config.get("task") if isinstance(config.get("task"), dict) else {}
    task_path = str(task_cfg.get("path") or "")
    task_name = Path(task_path).name if task_path else trial_dir.name.split("__")[0]
    trial_name = str(config.get("trial_name") or trial_dir.name)
    steps = _load_steps(trial_dir)
    metrics = _trajectory_metrics(trial_dir)
    started_at = steps[0].get("timestamp") if steps else _utc_now()
    finished_at = _utc_now()
    agent_cfg = config.get("agent") if isinstance(config.get("agent"), dict) else {}
    model_name = str(agent_cfg.get("model_name") or "")
    provider, _, model_short = model_name.partition("/")
    if not model_short:
        model_short = model_name
    return {
        "id": str(uuid.uuid4()),
        "task_name": task_name,
        "trial_name": trial_name,
        "trial_uri": trial_dir.as_uri(),
        "task_id": {"path": task_path},
        "source": str(task_cfg.get("source") or "tasks"),
        "task_checksum": None,
        "config": config,
        "agent_info": {
            "name": str(agent_cfg.get("name") or "unknown"),
            "version": "synthetic-early-stop",
            "model_info": {
                "name": model_short,
                "provider": provider or None,
            },
        },
        "agent_result": {
            "n_input_tokens": metrics.get("prompt_tokens", 0),
            "n_cache_tokens": metrics.get("cache_tokens", 0),
            "n_output_tokens": metrics.get("completion_tokens", 0),
            "cost_usd": None,
            "rollout_details": [],
            "metadata": {
                "n_episodes": len([s for s in steps if s.get("source") == "agent"]),
                "n_rounds": len([s for s in steps if s.get("source") == "agent"]),
                "summarization_count": 0,
                "intra_attempt_early_stop": True,
                "intra_attempt_early_stop_reason": reason,
            },
        },
        "verifier_result": {"rewards": {"reward": 0.0}},
        "exception_info": {
            "exception_type": "IntraAttemptEarlyStop",
            "exception_message": reason,
            "exception_traceback": None,
            "occurred_at": finished_at,
        },
        "started_at": started_at,
        "finished_at": finished_at,
        "environment_setup": {"started_at": None, "finished_at": None},
        "agent_setup": {"started_at": None, "finished_at": None},
        "agent_execution": {"started_at": started_at, "finished_at": finished_at},
        "verifier": {"started_at": None, "finished_at": None},
    }


def _mark_trial_early_stopped(trial_dir: Path, reason: str) -> None:
    verifier_dir = trial_dir / "verifier"
    verifier_dir.mkdir(parents=True, exist_ok=True)
    (verifier_dir / "reward.txt").write_text("0\n", encoding="utf-8")
    (verifier_dir / "early_stop_reason.txt").write_text(reason + "\n", encoding="utf-8")
    _write_json(
        trial_dir / "early_stop.json",
        {
            "triggered_at": _utc_now(),
            "reason": reason,
            "trial_dir": str(trial_dir),
        },
    )
    result_path = trial_dir / "result.json"
    if not result_path.exists():
        _write_json(result_path, _build_synthetic_result(trial_dir, reason))


def _should_early_stop(
    trial_dir: Path,
    args: argparse.Namespace,
    intra_context: dict[str, Any],
) -> tuple[bool, str | None]:
    if (trial_dir / "result.json").exists():
        return False, None
    if _verifier_started(trial_dir):
        return False, None
    steps = _load_steps(trial_dir)
    if not steps:
        return False, None
    patch_detected: bool | None = False
    if intra_context.get("strategy") == EARLY_STOP_STRATEGY_PAPER_DYNAMIC_TURN:
        patch_detected = _workspace_has_non_empty_patch(trial_dir)
    last_agent_ts = None
    for step in reversed(steps):
        if step.get("source") == "agent":
            last_agent_ts = _iso_to_ts(step.get("timestamp"))
            break
    if last_agent_ts is None:
        last_agent_ts = time.time()
    return should_early_stop_for_steps(
        steps,
        args,
        intra_context,
        current_ts=last_agent_ts,
        verifier_started=False,
        patch_detected=patch_detected,
    )


def _terminate_process_tree(proc: subprocess.Popen[Any], grace_seconds: float) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.time() + grace_seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            return
        time.sleep(0.5)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def main() -> int:
    args = parse_args()
    intra_context = _load_intra_attempt_context(args)
    print(
        f"[early-stop-policy] task={args.task_name} strategy={args.early_stop_strategy} "
        f"policy={intra_context['policy']} guidance={intra_context['recommendation'].get('guidance','')}",
        file=sys.stderr,
        flush=True,
    )
    harbor_args = list(args.harbor_args)
    if harbor_args and harbor_args[0] == "--":
        harbor_args = harbor_args[1:]
    if not harbor_args:
        print("missing harbor args", file=sys.stderr)
        return 2

    job_dir = args.jobs_root / args.job_name
    cmd = ["harbor", "run", *harbor_args]
    proc = subprocess.Popen(
        cmd,
        cwd=str(args.skillsbench_root),
        stdout=sys.stdout,
        stderr=sys.stderr,
        preexec_fn=os.setsid,
    )

    triggered_reason: str | None = None
    triggered_trial: Path | None = None

    try:
        while True:
            ret = proc.poll()
            if ret is not None:
                if triggered_reason is not None:
                    return 0
                return ret

            if job_dir.exists():
                active_trials = sorted(
                    [
                        path
                        for path in job_dir.iterdir()
                        if path.is_dir() and path.name.startswith(f"{args.task_name}__")
                    ],
                    key=lambda p: p.name,
                )
                for trial_dir in active_trials:
                    should_stop, reason = _should_early_stop(trial_dir, args, intra_context)
                    if should_stop and reason:
                        triggered_reason = reason
                        triggered_trial = trial_dir
                        print(
                            f"[early-stop] {trial_dir.name}: {reason}",
                            file=sys.stderr,
                            flush=True,
                        )
                        _mark_trial_early_stopped(trial_dir, reason)
                        _terminate_process_tree(proc, args.grace_seconds)
                        break
                if triggered_reason is not None:
                    continue

            time.sleep(args.poll_seconds)
    finally:
        if triggered_reason and triggered_trial is not None:
            _mark_trial_early_stopped(triggered_trial, triggered_reason)


if __name__ == "__main__":
    raise SystemExit(main())
