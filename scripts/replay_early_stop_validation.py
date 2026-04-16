#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from early_stop_policy import (  # noqa: E402
    TaskStaticInfo,
    decide_inter_attempt_stop,
    load_historical_tasks,
    recommend_intra_attempt_mode,
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


def replay_task(task: dict[str, Any], historical_tasks: list[dict[str, Any]], prices: dict[str, float]) -> dict[str, Any]:
    task_id = str(task.get("task_id") or "")
    recommendation = recommend_intra_attempt_mode(TaskStaticInfo(task_id=task_id), historical_tasks)
    attempts = list(task.get("attempts") or [])
    kept_attempts: list[dict[str, Any]] = []
    stop_reason: str | None = None
    inter_decisions: list[dict[str, Any]] = []

    if attempts:
        kept_attempts.append(attempts[0])

    for idx in range(1, len(attempts)):
        if kept_attempts and execution_was_intra_attempt_early_stopped((kept_attempts[-1].get("execution") or {})):
            stop_reason = "intra-attempt-early-stop"
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

    original_cost = sum(attempt_cost_cny(attempt, prices) for attempt in attempts)
    kept_cost = sum(attempt_cost_cny(attempt, prices) for attempt in kept_attempts)

    return {
        "task_id": task_id,
        "status": task.get("status"),
        "original_attempt_count": len(attempts),
        "kept_attempt_count": len(kept_attempts),
        "original_cost_cny": round(original_cost, 6),
        "kept_cost_cny": round(kept_cost, 6),
        "saved_cost_cny": round(original_cost - kept_cost, 6),
        "stop_reason": stop_reason,
        "intra_attempt_policy": recommendation["policy"],
        "intra_attempt_guidance": recommendation["guidance"],
        "neighbor_cases": recommendation["neighbor_cases"],
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

    results = [replay_task(task, historical_tasks, prices) for task in tasks]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
