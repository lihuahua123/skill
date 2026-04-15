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
    parser.add_argument("--max-agent-steps", type=int, default=int(os.environ.get("SKILLSBENCH_EARLY_STOP_MAX_AGENT_STEPS", "28")))
    parser.add_argument("--max-minutes-without-verifier", type=float, default=float(os.environ.get("SKILLSBENCH_EARLY_STOP_MAX_MINUTES_WITHOUT_VERIFIER", "15")))
    parser.add_argument("--recent-window", type=int, default=int(os.environ.get("SKILLSBENCH_EARLY_STOP_RECENT_WINDOW", "8")))
    parser.add_argument("--recent-plan-ratio", type=float, default=float(os.environ.get("SKILLSBENCH_EARLY_STOP_RECENT_PLAN_RATIO", "0.75")))
    parser.add_argument("--grace-seconds", type=float, default=20.0)
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


def _should_early_stop(trial_dir: Path, args: argparse.Namespace) -> tuple[bool, str | None]:
    if (trial_dir / "result.json").exists():
        return False, None
    if _verifier_started(trial_dir):
        return False, None
    steps = _load_steps(trial_dir)
    if not steps:
        return False, None

    agent_steps = [s for s in steps if s.get("source") == "agent"]
    if len(agent_steps) < max(4, min(args.max_agent_steps, args.recent_window)):
        return False, None

    first_ts = _iso_to_ts(agent_steps[0].get("timestamp"))
    runtime_minutes = 0.0
    if first_ts is not None:
        runtime_minutes = (time.time() - first_ts) / 60.0

    agent_messages = [str(s.get("message") or "") for s in agent_steps]
    recent_ratio = _recent_plan_ratio(agent_messages, args.recent_window)
    repeated_deliverable_claims = sum(
        1 for msg in agent_messages[-args.recent_window :]
        if re.search(r"all required|deliverables have been created|created successfully", msg, re.IGNORECASE)
    )

    if (
        len(agent_steps) >= args.max_agent_steps
        and runtime_minutes >= args.max_minutes_without_verifier
        and recent_ratio >= args.recent_plan_ratio
    ):
        return True, (
            f"intra-attempt early stop: {len(agent_steps)} agent steps, "
            f"{runtime_minutes:.1f}m without verifier, recent plan ratio {recent_ratio:.2f}"
        )

    if (
        len(agent_steps) >= args.max_agent_steps + 6
        and runtime_minutes >= args.max_minutes_without_verifier / 2
        and repeated_deliverable_claims >= 2
    ):
        return True, (
            f"intra-attempt early stop: repeated completion claims without verifier "
            f"after {len(agent_steps)} agent steps"
        )

    return False, None


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
                    should_stop, reason = _should_early_stop(trial_dir, args)
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
