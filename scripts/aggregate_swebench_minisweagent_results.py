#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate mini-swe-agent SWE-bench run outputs into the retry analysis schema."
    )
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--max-task-attempts", type=int, default=1)
    parser.add_argument("--benchmark-version", default="swebench_verified")
    parser.add_argument("--feedback-policy", default="none")
    parser.add_argument("--feedback-format", default="none")
    parser.add_argument("--feedback-answer-safety", default="no-answers")
    parser.add_argument("--stop-rule", default="max-attempts-only")
    parser.add_argument("--stop-threshold", default="0.0")
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def build_usage(model_stats: dict[str, Any]) -> dict[str, Any]:
    api_calls = int(model_stats.get("api_calls", 0) or 0)
    cost_usd = float(model_stats.get("instance_cost", 0.0) or 0.0)
    return {
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "cost_usd": cost_usd,
        "requests": api_calls,
    }


def build_attempt_record(
    attempt_summary: dict[str, Any],
    *,
    default_feedback_policy: str,
    default_feedback_format: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    traj = json.loads(Path(attempt_summary["traj_json"]).read_text(encoding="utf-8"))
    eval_result = json.loads(Path(attempt_summary["eval_json"]).read_text(encoding="utf-8"))
    model_stats = (traj.get("info") or {}).get("model_stats") or {}
    usage = build_usage(model_stats)
    resolved = bool(eval_result.get("resolved"))
    transcript_length = len(traj.get("messages") or [])
    execution_time = float(attempt_summary.get("agent_time_seconds", 0.0) or 0.0) + float(
        attempt_summary.get("evaluation_time_seconds", 0.0) or 0.0
    )
    feedback_prompt = attempt_summary.get("feedback_prompt")
    feedback_stats = attempt_summary.get("feedback_prompt_stats") or {
        "text_length_chars": 0,
        "stable_prefix_length_chars": 0,
        "dynamic_suffix_length_chars": 0,
    }
    attempt_record = {
        "attempt": int(attempt_summary.get("attempt", 0) or 0),
        "instruction_kind": "retry" if feedback_prompt else "initial",
        "feedback_prompt": feedback_prompt,
        "feedback_prompt_stats": feedback_stats,
        "feedback_policy": attempt_summary.get("feedback_policy") or default_feedback_policy,
        "feedback_format": attempt_summary.get("feedback_format") or default_feedback_format,
        "execution": {
            "llm_rounds": int(model_stats.get("api_calls", 0) or 0),
            "usage": usage,
            "usage_per_round": [],
            "execution_time": execution_time,
            "error": {},
        },
        "verifier": {
            "resolved": resolved,
            "report_path": eval_result.get("report_path"),
            "test_output_path": eval_result.get("test_output_path"),
            "notes": eval_result.get("notes"),
        },
        "grading": {
            "score": 1.0 if resolved else 0.0,
            "max_score": 1.0,
            "passed": resolved,
            "criteria": [
                {
                    "criterion": "overall",
                    "score": 1.0 if resolved else 0.0,
                    "max_score": 1.0,
                }
            ],
        },
        "artifact_paths": {
            "traj_json": attempt_summary["traj_json"],
            "eval_json": attempt_summary["eval_json"],
            "prediction_json": attempt_summary["prediction_json"],
            "feedback_txt": attempt_summary.get("feedback_path") or "",
        },
        "unresolved_criteria_count": 0 if resolved else 1,
        "stop_rule": attempt_summary.get("stop_rule"),
        "stop_rule_threshold": attempt_summary.get("stop_threshold"),
        "stop_rule_trigger_reason": attempt_summary.get("stop_rule_trigger_reason"),
    }
    aggregate_fields = {
        "resolved": resolved,
        "usage": usage,
        "transcript_length": transcript_length,
        "execution_time": execution_time,
        "feedback_length_chars": int(feedback_stats.get("text_length_chars", 0) or 0),
    }
    return attempt_record, aggregate_fields


def build_task(instance_root: Path) -> dict[str, Any]:
    summary = json.loads((instance_root / "task_summary.json").read_text(encoding="utf-8"))
    retry_policies = summary.get("retry_policies") or {}
    attempts: list[dict[str, Any]] = []
    attempt_aggregates: list[dict[str, Any]] = []
    for attempt_summary in summary.get("attempts") or []:
        attempt_record, aggregate_fields = build_attempt_record(
            attempt_summary,
            default_feedback_policy=retry_policies.get("feedback_policy", "none"),
            default_feedback_format=retry_policies.get("feedback_format", "none"),
        )
        attempts.append(attempt_record)
        attempt_aggregates.append(aggregate_fields)

    usage = {
        "total_tokens": sum(int((item["usage"].get("total_tokens", 0) or 0)) for item in attempt_aggregates),
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "cost_usd": sum(float(item["usage"]["cost_usd"]) for item in attempt_aggregates),
        "requests": sum(int(item["usage"]["requests"]) for item in attempt_aggregates),
    }
    resolved = bool(summary.get("success_within_budget"))
    execution_time = sum(float(item["execution_time"]) for item in attempt_aggregates)
    transcript_length = sum(int(item["transcript_length"] or 0) for item in attempt_aggregates)

    return {
        "task_id": summary["task_id"],
        "task_prompt": None,
        "status": "passed" if resolved else "failed",
        "timed_out": False,
        "execution_time": execution_time,
        "transcript_length": transcript_length,
        "llm_rounds": sum(int((item["usage"].get("requests", 0) or 0)) for item in attempt_aggregates),
        "usage": usage,
        "usage_per_round": [],
        "workspace": {},
        "grading": {
            "score": 1.0 if resolved else 0.0,
            "max_score": 1.0,
            "passed": resolved,
            "criteria": [
                {
                    "criterion": "overall",
                    "score": 1.0 if resolved else 0.0,
                    "max_score": 1.0,
                }
            ],
        },
        "grading_summary": {
            "score": 1.0 if resolved else 0.0,
            "max_score": 1.0,
            "passed": resolved,
        },
        "completion": {"passed": resolved},
        "frontmatter": {},
        "attempt_count": int(summary.get("attempt_count", len(attempts)) or len(attempts)),
        "first_success_attempt": summary.get("first_success_attempt"),
        "success_within_budget": bool(summary.get("success_within_budget")),
        "unresolved_criteria_count_by_attempt": [
            int(attempt.get("unresolved_criteria_count") or 0) for attempt in attempts
        ],
        "transcript_length_by_attempt": [item["transcript_length"] for item in attempt_aggregates],
        "prompt_tokens_by_attempt": [0 for _ in attempts],
        "completion_tokens_by_attempt": [0 for _ in attempts],
        "feedback_length_chars_by_attempt": [item["feedback_length_chars"] for item in attempt_aggregates],
        "stop_reason": summary.get("stop_reason", "max-attempts-reached"),
        "attempts": attempts,
        "retry_policies": retry_policies,
    }


def build_efficiency(tasks: list[dict[str, Any]], max_task_attempts: int) -> dict[str, Any]:
    n_tasks = len(tasks)
    total_cost = sum(float(task["usage"]["cost_usd"]) for task in tasks)
    total_requests = sum(int(task["usage"]["requests"]) for task in tasks)
    total_time = sum(float(task["execution_time"]) for task in tasks)
    success_count = sum(1 for task in tasks if task["first_success_attempt"] is not None)
    success_at_k = {}
    for k in range(1, max(1, max_task_attempts) + 1):
        success_at_k[str(k)] = round(
            sum(
                1
                for task in tasks
                if isinstance(task.get("first_success_attempt"), int)
                and int(task["first_success_attempt"]) <= k
            )
            / n_tasks,
            6,
        ) if n_tasks else 0.0

    return {
        "total_tokens": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cache_write_tokens": 0,
        "total_cost_usd": round(total_cost, 8),
        "total_requests": total_requests,
        "total_execution_time_seconds": round(total_time, 6),
        "tasks_with_usage_data": len(tasks),
        "tokens_per_task": 0.0,
        "cost_per_task_usd": round((total_cost / n_tasks) if n_tasks else 0.0, 8),
        "score_per_1k_tokens": None,
        "score_per_dollar": round(success_count / total_cost, 8) if total_cost > 0 else None,
        "success_rate": round((success_count / n_tasks) if n_tasks else 0.0, 6),
        "success_per_1k_tokens": None,
        "success_per_dollar": round(success_count / total_cost, 8) if total_cost > 0 else None,
        "success_at_k": success_at_k,
        "per_task": [
            {
                "task_id": task["task_id"],
                "success": task["first_success_attempt"] is not None,
                "first_success_attempt": task["first_success_attempt"],
                "attempt_count": task["attempt_count"],
                "total_tokens": 0,
                "cost_usd": round(float(task["usage"]["cost_usd"]), 8),
            }
            for task in tasks
        ],
    }


def main() -> None:
    args = parse_args()
    task_roots = sorted(
        path for path in args.run_root.iterdir() if path.is_dir() and (path / "task_summary.json").exists()
    )
    tasks = [build_task(task_root) for task_root in task_roots]
    payload = {
        "model": args.model,
        "benchmark": "swebench",
        "benchmark_version": args.benchmark_version,
        "agent_temperature": 0.0,
        "run_id": args.run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "suite": args.suite,
        "runs_per_task": 1,
        "max_task_attempts": max(1, args.max_task_attempts),
        "retry_policies": {
            "feedback_policy": args.feedback_policy,
            "feedback_format": args.feedback_format,
            "feedback_strategy": "swebench-safe",
            "feedback_answer_safety": args.feedback_answer_safety,
            "stop_rule": args.stop_rule,
            "stop_threshold": args.stop_threshold,
            "early_stop_intra_attempt": False,
            "early_stop_strategy": "none",
        },
        "tasks": tasks,
        "efficiency": build_efficiency(tasks, max(1, args.max_task_attempts)),
        "source": {
            "run_root": str(args.run_root),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
