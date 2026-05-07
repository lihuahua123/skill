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
    api_calls = int(model_stats["api_calls"])
    cost_usd = float(model_stats["instance_cost"])
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


def build_task(instance_root: Path) -> dict[str, Any]:
    summary = json.loads((instance_root / "task_summary.json").read_text(encoding="utf-8"))
    attempt_summary = summary["attempts"][0]
    traj = json.loads(Path(attempt_summary["traj_json"]).read_text(encoding="utf-8"))
    eval_result = json.loads(Path(attempt_summary["eval_json"]).read_text(encoding="utf-8"))

    model_stats = traj["info"]["model_stats"]
    usage = build_usage(model_stats)
    resolved = bool(eval_result["resolved"])
    transcript_length = len(traj["messages"])
    execution_time = float(attempt_summary["agent_time_seconds"]) + float(attempt_summary["evaluation_time_seconds"])

    attempt_record = {
        "attempt": 1,
        "instruction_kind": "initial",
        "feedback_prompt": None,
        "feedback_prompt_stats": {"chars": 0, "tokens_estimate": 0},
        "feedback_policy": "none",
        "feedback_format": "none",
        "execution": {
            "llm_rounds": int(model_stats["api_calls"]),
            "usage": usage,
            "usage_per_round": [],
            "execution_time": execution_time,
            "error": {},
        },
        "verifier": {
            "resolved": resolved,
            "report_path": eval_result["report_path"],
            "test_output_path": eval_result["test_output_path"],
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
        },
    }

    return {
        "task_id": summary["task_id"],
        "task_prompt": None,
        "status": "passed" if resolved else "failed",
        "timed_out": False,
        "execution_time": execution_time,
        "transcript_length": transcript_length,
        "llm_rounds": int(model_stats["api_calls"]),
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
        "attempt_count": 1,
        "first_success_attempt": 1 if resolved else None,
        "success_within_budget": resolved,
        "unresolved_criteria_count_by_attempt": [0 if resolved else 1],
        "transcript_length_by_attempt": [transcript_length],
        "prompt_tokens_by_attempt": [0],
        "completion_tokens_by_attempt": [0],
        "feedback_length_chars_by_attempt": [0],
        "stop_reason": "passed" if resolved else "exhausted",
        "attempts": [attempt_record],
    }


def build_efficiency(tasks: list[dict[str, Any]], max_task_attempts: int) -> dict[str, Any]:
    n_tasks = len(tasks)
    total_cost = sum(float(task["usage"]["cost_usd"]) for task in tasks)
    total_requests = sum(int(task["usage"]["requests"]) for task in tasks)
    total_time = sum(float(task["execution_time"]) for task in tasks)
    success_count = sum(1 for task in tasks if task["first_success_attempt"] is not None)
    success_at_k = {}
    for k in range(1, max(1, max_task_attempts) + 1):
        success_at_k[str(k)] = round(success_count / n_tasks, 6) if n_tasks else 0.0

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
            "feedback_strategy": "none",
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
