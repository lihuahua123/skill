#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from types import SimpleNamespace

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from early_stop_policy import (  # noqa: E402
    build_attempt_verifier_summary,
    TaskStaticInfo,
    decide_inter_attempt_stop,
    load_historical_tasks,
    recommend_intra_attempt_mode,
)
from run_skillsbench_with_early_stop import (  # noqa: E402
    _iso_to_ts,
    should_early_stop_for_steps,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay historical SkillsBench attempts against the current early-stop policy."
    )
    parser.add_argument(
        "--aggregated-results",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "analysis" / "rq1" / "aggregated_results.json",
    )
    parser.add_argument(
        "--token-pricing",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "analysis" / "rq1" / "token_pricing_cny_per_mtoken.json",
    )
    parser.add_argument(
        "--task-id",
        action="append",
        dest="task_ids",
        default=[],
        help="Task id to replay. Can be supplied multiple times.",
    )
    parser.add_argument(
        "--jobs-root",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "skillsbench" / "jobs",
        help="Local SkillsBench jobs root used to resolve trial trajectory.json files for intra-attempt replay.",
    )
    parser.add_argument(
        "--replay-jobs",
        action="store_true",
        help="Replay local jobs_root trials directly. This validates intra-attempt early-stop on trials with trajectory.json.",
    )
    parser.add_argument(
        "--job-name",
        action="append",
        dest="job_names",
        default=[],
        help="Job directory name under jobs_root. Can be supplied multiple times.",
    )
    parser.add_argument("--max-agent-steps", type=int, default=28)
    parser.add_argument("--max-minutes-without-verifier", type=float, default=15.0)
    parser.add_argument("--recent-window", type=int, default=8)
    parser.add_argument("--recent-plan-ratio", type=float, default=0.75)
    return parser.parse_args()


def compute_cost_cny(usage: dict[str, Any], prices: dict[str, float]) -> float:
    usage = usage or {}
    return (
        float(usage.get("input_tokens") or 0) / 1_000_000 * prices["input_tokens"]
        + float(usage.get("output_tokens") or 0) / 1_000_000 * prices["output_tokens"]
        + float(usage.get("cache_read_tokens") or usage.get("cache_tokens") or 0) / 1_000_000 * prices["cache_read_tokens"]
    )


def attempt_cost_cny(attempt: dict[str, Any], prices: dict[str, float]) -> float:
    execution = (attempt.get("execution") or {}) if isinstance(attempt, dict) else {}
    usage = (execution.get("usage") or attempt.get("usage") or {}) if isinstance(execution, dict) else {}
    return compute_cost_cny(usage, prices)


def execution_was_intra_attempt_early_stopped(execution: dict[str, Any]) -> bool:
    if not isinstance(execution, dict):
        return False
    if bool(execution.get("intra_attempt_early_stop")):
        return True
    metadata = execution.get("metadata")
    if isinstance(metadata, dict) and bool(metadata.get("intra_attempt_early_stop")):
        return True
    agent_result = execution.get("agent_result")
    if isinstance(agent_result, dict):
        agent_metadata = agent_result.get("metadata")
        if isinstance(agent_metadata, dict) and bool(agent_metadata.get("intra_attempt_early_stop")):
            return True
    exception = execution.get("exception_info")
    if isinstance(exception, dict) and exception.get("exception_type") == "IntraAttemptEarlyStop":
        return True
    return False


def _build_replay_policy_args(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        max_agent_steps=args.max_agent_steps,
        max_minutes_without_verifier=args.max_minutes_without_verifier,
        recent_window=args.recent_window,
        recent_plan_ratio=args.recent_plan_ratio,
    )


def _attempt_passed(attempt: dict[str, Any]) -> bool:
    return build_attempt_verifier_summary(attempt).passed


def _resolve_trial_dir(attempt: dict[str, Any], jobs_root: Path) -> Path | None:
    execution = attempt.get("execution") or {}
    agent_dir = execution.get("agent_dir")
    if not agent_dir:
        return None
    agent_path = Path(str(agent_dir))
    trial_name = agent_path.parts[-3] if len(agent_path.parts) >= 3 else ""
    if not trial_name:
        return None

    direct = jobs_root / trial_name
    if (direct / "agent" / "trajectory.json").exists():
        return direct

    job_name = agent_path.parts[-4] if len(agent_path.parts) >= 4 else ""
    nested = jobs_root / job_name / trial_name
    if (nested / "agent" / "trajectory.json").exists():
        return nested

    matches = list(jobs_root.glob(f"*/{trial_name}/agent/trajectory.json"))
    if len(matches) == 1:
        return matches[0].parents[1]

    return None


def _load_trial_steps(trial_dir: Path | None) -> list[dict[str, Any]]:
    if trial_dir is None:
        return []
    trajectory_path = trial_dir / "agent" / "trajectory.json"
    if not trajectory_path.exists():
        return []
    payload = json.loads(trajectory_path.read_text(encoding="utf-8"))
    steps = payload.get("steps")
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, dict)]


def replay_intra_attempt_stop(
    task_id: str,
    attempt: dict[str, Any],
    historical_tasks: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    recommendation = recommend_intra_attempt_mode(TaskStaticInfo(task_id=task_id), historical_tasks)
    trial_dir = _resolve_trial_dir(attempt, args.jobs_root)
    steps = _load_trial_steps(trial_dir)
    if not steps:
        return {
            "trace_available": False,
            "trial_dir": str(trial_dir) if trial_dir else None,
            "policy": recommendation["policy"],
            "guidance": recommendation["guidance"],
            "would_stop": False,
            "stop_reason": None,
            "triggered_after_agent_steps": None,
            "total_agent_steps": None,
        }

    intra_context = {
        "task_info": TaskStaticInfo(task_id=task_id),
        "historical_tasks": historical_tasks,
        "recommendation": recommendation,
        "policy": recommendation["policy"],
    }
    replay_args = _build_replay_policy_args(args)
    total_agent_steps = sum(1 for step in steps if step.get("source") == "agent")

    for end_idx, step in enumerate(steps, start=1):
        if step.get("source") != "agent":
            continue
        current_ts = _iso_to_ts(step.get("timestamp"))
        should_stop, reason = should_early_stop_for_steps(
            steps[:end_idx],
            replay_args,
            intra_context,
            current_ts=current_ts,
            verifier_started=False,
        )
        if should_stop:
            triggered_after_agent_steps = sum(1 for item in steps[:end_idx] if item.get("source") == "agent")
            return {
                "trace_available": True,
                "trial_dir": str(trial_dir),
                "policy": recommendation["policy"],
                "guidance": recommendation["guidance"],
                "would_stop": True,
                "stop_reason": reason,
                "triggered_after_agent_steps": triggered_after_agent_steps,
                "total_agent_steps": total_agent_steps,
            }

    return {
        "trace_available": True,
        "trial_dir": str(trial_dir),
        "policy": recommendation["policy"],
        "guidance": recommendation["guidance"],
        "would_stop": False,
        "stop_reason": None,
        "triggered_after_agent_steps": None,
        "total_agent_steps": total_agent_steps,
    }


def _trial_passed_from_result(result_payload: dict[str, Any]) -> bool:
    verifier_result = result_payload.get("verifier_result")
    if isinstance(verifier_result, dict):
        rewards = verifier_result.get("rewards")
        if isinstance(rewards, dict):
            reward = rewards.get("reward")
            try:
                return float(reward or 0.0) >= 1.0
            except (TypeError, ValueError):
                return False
    return False


def _trial_cost_cny_from_result(result_payload: dict[str, Any], prices: dict[str, float]) -> float:
    agent_result = result_payload.get("agent_result")
    if not isinstance(agent_result, dict):
        return 0.0
    usage = {
        "input_tokens": agent_result.get("n_input_tokens") or 0,
        "output_tokens": agent_result.get("n_output_tokens") or 0,
        "cache_read_tokens": agent_result.get("n_cache_tokens") or 0,
    }
    return compute_cost_cny(usage, prices)


def _iter_trial_dirs(jobs_root: Path, job_names: list[str]) -> list[Path]:
    if job_names:
        job_dirs = [jobs_root / name for name in job_names]
    else:
        job_dirs = [path for path in jobs_root.iterdir() if path.is_dir()] if jobs_root.exists() else []

    trial_dirs: list[Path] = []
    for job_dir in sorted(job_dirs):
        if not job_dir.exists() or not job_dir.is_dir():
            continue
        for trial_dir in sorted(path for path in job_dir.iterdir() if path.is_dir()):
            if (trial_dir / "agent" / "trajectory.json").exists() and (trial_dir / "result.json").exists():
                trial_dirs.append(trial_dir)
    return trial_dirs


def replay_local_trial(
    trial_dir: Path,
    historical_tasks: list[dict[str, Any]],
    prices: dict[str, float],
    args: argparse.Namespace,
) -> dict[str, Any]:
    result_payload = json.loads((trial_dir / "result.json").read_text(encoding="utf-8"))
    task_id = str(result_payload.get("task_name") or trial_dir.name.split("__")[0])
    steps = _load_trial_steps(trial_dir)
    recommendation = recommend_intra_attempt_mode(TaskStaticInfo(task_id=task_id), historical_tasks)
    intra_context = {
        "task_info": TaskStaticInfo(task_id=task_id),
        "historical_tasks": historical_tasks,
        "recommendation": recommendation,
        "policy": recommendation["policy"],
    }
    replay_args = _build_replay_policy_args(args)
    stop_reason = None
    triggered_after_agent_steps = None
    total_agent_steps = sum(1 for step in steps if step.get("source") == "agent")

    for end_idx, step in enumerate(steps, start=1):
        if step.get("source") != "agent":
            continue
        current_ts = _iso_to_ts(step.get("timestamp"))
        should_stop, reason = should_early_stop_for_steps(
            steps[:end_idx],
            replay_args,
            intra_context,
            current_ts=current_ts,
            verifier_started=False,
        )
        if should_stop:
            stop_reason = reason
            triggered_after_agent_steps = sum(1 for item in steps[:end_idx] if item.get("source") == "agent")
            break

    return {
        "job_name": trial_dir.parent.name,
        "trial_name": trial_dir.name,
        "task_id": task_id,
        "passed": _trial_passed_from_result(result_payload),
        "attempt_cost_cny": round(_trial_cost_cny_from_result(result_payload, prices), 6),
        "policy": recommendation["policy"],
        "guidance": recommendation["guidance"],
        "trace_available": bool(steps),
        "would_stop": stop_reason is not None,
        "stop_reason": stop_reason,
        "triggered_after_agent_steps": triggered_after_agent_steps,
        "total_agent_steps": total_agent_steps,
    }


def summarize_local_trial_replays(trial_results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(trial_results)
    triggered = [item for item in trial_results if item.get("would_stop")]
    original_passed = sum(1 for item in trial_results if item.get("passed"))
    replay_passed = sum(1 for item in trial_results if item.get("passed") and not item.get("would_stop"))
    blocked_costs = [float(item.get("attempt_cost_cny") or 0.0) for item in triggered]
    blocked_cost_total = sum(blocked_costs)
    return {
        "trial_count": total,
        "triggered_trial_count": len(triggered),
        "trigger_rate": (len(triggered) / total) if total else 0.0,
        "original_pass_rate": (original_passed / total) if total else 0.0,
        "replay_pass_rate": (replay_passed / total) if total else 0.0,
        "pass_rate_delta": ((replay_passed - original_passed) / total) if total else 0.0,
        "blocked_cost_total_cny": round(blocked_cost_total, 6),
        "blocked_cost_mean_cny": round((blocked_cost_total / len(triggered)) if triggered else 0.0, 6),
    }


def replay_task(
    task: dict[str, Any],
    historical_tasks: list[dict[str, Any]],
    prices: dict[str, float],
    args: argparse.Namespace,
) -> dict[str, Any]:
    task_id = str(task.get("task_id") or "")
    attempts = list(task.get("attempts") or [])
    kept_attempts: list[dict[str, Any]] = []
    stop_reason: str | None = None
    inter_decisions: list[dict[str, Any]] = []
    intra_replays: list[dict[str, Any]] = []
    cost_is_exact = True
    cost_note = "exact"

    if attempts:
        kept_attempts.append(attempts[0])

    for idx in range(1, len(attempts)):
        if kept_attempts:
            last_attempt = kept_attempts[-1]
            intra_replay = replay_intra_attempt_stop(task_id, last_attempt, historical_tasks, args)
            intra_replays.append(
                {
                    "attempt": last_attempt.get("attempt"),
                    **intra_replay,
                }
            )
        else:
            intra_replay = {"would_stop": False, "trace_available": False}

        if intra_replay["would_stop"]:
            stop_reason = intra_replay["stop_reason"] or "intra-attempt-early-stop"
            cost_is_exact = False
            cost_note = "kept_cost_cny is an upper bound because trace replay stops inside the last kept attempt"
            break
        if kept_attempts and execution_was_intra_attempt_early_stopped((kept_attempts[-1].get("execution") or {})):
            stop_reason = "intra-attempt-early-stop"
            cost_is_exact = False
            cost_note = "kept_cost_cny is an upper bound because historical execution already marked intra-attempt early stop"
            break

        previous_attempt = attempts[idx - 1]
        current_attempt = attempts[idx]
        decision = decide_inter_attempt_stop(previous_attempt, current_attempt)
        inter_decisions.append(
            {
                "from_attempt": idx,
                "to_attempt": idx + 1,
                "should_stop": decision.should_stop,
                "reason": decision.reason,
                "evidence": list(decision.evidence),
            }
        )
        if decision.should_stop:
            stop_reason = decision.reason
            break
        kept_attempts.append(current_attempt)

    if kept_attempts and len(intra_replays) < len(kept_attempts):
        last_attempt = kept_attempts[-1]
        intra_replays.append(
            {
                "attempt": last_attempt.get("attempt"),
                **replay_intra_attempt_stop(task_id, last_attempt, historical_tasks, args),
            }
        )

    original_cost = sum(attempt_cost_cny(attempt, prices) for attempt in attempts)
    kept_cost = sum(attempt_cost_cny(attempt, prices) for attempt in kept_attempts)
    replay_success = any(_attempt_passed(attempt) for attempt in kept_attempts)

    return {
        "task_id": task_id,
        "status": task.get("status"),
        "original_attempt_count": len(attempts),
        "kept_attempt_count": len(kept_attempts),
        "original_success": any(_attempt_passed(attempt) for attempt in attempts),
        "replay_success": replay_success,
        "original_cost_cny": round(original_cost, 6),
        "kept_cost_cny": round(kept_cost, 6),
        "saved_cost_cny": round(original_cost - kept_cost, 6),
        "cost_is_exact": cost_is_exact,
        "cost_note": cost_note,
        "stop_reason": stop_reason,
        "intra_attempt_replays": intra_replays,
        "inter_attempt_decisions": inter_decisions,
    }


def main() -> int:
    args = parse_args()
    aggregated = json.loads(args.aggregated_results.read_text(encoding="utf-8"))
    historical_tasks = load_historical_tasks(args.aggregated_results)
    prices = json.loads(args.token_pricing.read_text(encoding="utf-8"))["MiniMax-M2.5"]
    tasks = list(aggregated.get("tasks") or [])

    if args.task_ids:
        wanted = set(args.task_ids)
        tasks = [task for task in tasks if str(task.get("task_id") or "") in wanted]

    if args.replay_jobs:
        trial_results = []
        for trial_dir in _iter_trial_dirs(args.jobs_root, args.job_names):
            task_name = trial_dir.name.split("__")[0]
            if args.task_ids and task_name not in wanted:
                continue
            trial_results.append(replay_local_trial(trial_dir, historical_tasks, prices, args))
        job_names = sorted({item["job_name"] for item in trial_results})
        summary = summarize_local_trial_replays(trial_results)
        print(
            json.dumps(
                {
                    "jobs": job_names,
                    "task_filter": args.task_ids,
                    "summary": summary,
                    "trials": trial_results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    results = [replay_task(task, historical_tasks, prices, args) for task in tasks]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
