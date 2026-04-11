#!/usr/bin/env python3
"""Aggregate RQ1 task results across multiple benchmark JSON files.

Selection priority for duplicate task results:
1. Successful task
2. Task with token usage
3. Newer task record (by task-level finish/start time, then file timestamp)

The chosen task record is preserved as-is so all task information remains
available, including attempts, verifier traces, error payloads, stdout/stderr
paths, failure types, and related metadata.
"""

from __future__ import annotations

import argparse
import copy
import glob
import json
import os
from collections import Counter
from datetime import datetime
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        default="/hy-tmp/skill/results/rq1",
        help="Directory containing RQ1 result JSON files.",
    )
    parser.add_argument(
        "--output",
        default="/hy-tmp/skill/analysis/rq1/aggregated_results.json",
        help="Path for aggregated JSON output.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation for the output file.",
    )
    return parser.parse_args()


def load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def extract_task_time(task: dict[str, Any]) -> datetime | None:
    attempts = task.get("attempts")
    if isinstance(attempts, list) and attempts:
        for attempt in reversed(attempts):
            finished = parse_iso_datetime(attempt.get("finished_at"))
            if finished is not None:
                return finished
        for attempt in reversed(attempts):
            started = parse_iso_datetime(attempt.get("started_at"))
            if started is not None:
                return started
    return None


def has_token_usage(task: dict[str, Any]) -> bool:
    usage = task.get("usage")
    if isinstance(usage, dict):
        for key in (
            "total_tokens",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "request_count",
        ):
            value = usage.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return True

    for key in (
        "prompt_tokens_by_attempt",
        "completion_tokens_by_attempt",
    ):
        values = task.get(key)
        if isinstance(values, list) and any(
            isinstance(v, (int, float)) and v > 0 for v in values
        ):
            return True

    attempts = task.get("attempts")
    if isinstance(attempts, list):
        for attempt in attempts:
            execution = attempt.get("execution")
            if not isinstance(execution, dict):
                continue
            attempt_usage = execution.get("usage")
            if not isinstance(attempt_usage, dict):
                continue
            for key in (
                "total_tokens",
                "input_tokens",
                "output_tokens",
                "cache_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
            ):
                value = attempt_usage.get(key)
                if isinstance(value, (int, float)) and value > 0:
                    return True
    return False


def is_success(task: dict[str, Any]) -> bool:
    if task.get("status") == "success":
        return True

    grading = task.get("grading")
    if isinstance(grading, dict):
        score = grading.get("score")
        max_score = grading.get("max_score")
        if isinstance(score, (int, float)) and isinstance(max_score, (int, float)):
            return max_score > 0 and score >= max_score

    completion = task.get("completion")
    if isinstance(completion, dict):
        mean = completion.get("mean")
        if isinstance(mean, (int, float)) and mean >= 1.0:
            return True

    return False


def task_sort_key(record: dict[str, Any]) -> tuple[int, int, float, float, str]:
    task = record["task"]
    task_dt = extract_task_time(task)
    task_ts = task_dt.timestamp() if task_dt is not None else float("-inf")
    file_ts = record.get("file_timestamp")
    if not isinstance(file_ts, (int, float)):
        file_ts = float("-inf")
    return (
        1 if is_success(task) else 0,
        1 if has_token_usage(task) else 0,
        task_ts,
        float(file_ts),
        record["source_file"],
    )


def build_record(task: dict[str, Any], run: dict[str, Any], source_file: str) -> dict[str, Any]:
    copied = copy.deepcopy(task)
    return {
        "task": copied,
        "source_file": source_file,
        "source_run_id": run.get("run_id"),
        "file_timestamp": run.get("timestamp"),
        "task_time": extract_task_time(copied),
        "success": is_success(copied),
        "has_tokens": has_token_usage(copied),
    }


def source_summary(record: dict[str, Any]) -> dict[str, Any]:
    task = record["task"]
    return {
        "source_file": record["source_file"],
        "source_run_id": record.get("source_run_id"),
        "file_timestamp": record.get("file_timestamp"),
        "task_id": task.get("task_id"),
        "status": task.get("status"),
        "success": record["success"],
        "has_tokens": record["has_tokens"],
        "stop_reason": task.get("stop_reason"),
        "timed_out": task.get("timed_out"),
        "llm_rounds": task.get("llm_rounds"),
        "attempt_count": task.get("attempt_count"),
        "usage": copy.deepcopy(task.get("usage")),
    }


def aggregate(input_dir: str) -> dict[str, Any]:
    files = sorted(glob.glob(os.path.join(input_dir, "*.json")))
    if not files:
        raise FileNotFoundError(f"No JSON files found in {input_dir}")

    task_candidates: dict[str, list[dict[str, Any]]] = {}
    runs = []

    for path in files:
        run = load_json(path)
        source_file = os.path.basename(path)
        runs.append(
            {
                "source_file": source_file,
                "run_id": run.get("run_id"),
                "timestamp": run.get("timestamp"),
                "suite": run.get("suite"),
                "task_count": len(run.get("tasks", [])),
            }
        )
        for task in run.get("tasks", []):
            task_id = task.get("task_id")
            if not task_id:
                continue
            task_candidates.setdefault(task_id, []).append(build_record(task, run, source_file))

    aggregated_tasks = []
    provenance = []

    for task_id in sorted(task_candidates):
        candidates = task_candidates[task_id]
        best = max(candidates, key=task_sort_key)
        chosen_task = copy.deepcopy(best["task"])
        chosen_task["_aggregation"] = {
            "selected_from": best["source_file"],
            "selected_run_id": best.get("source_run_id"),
            "selection_reason": {
                "success": best["success"],
                "has_tokens": best["has_tokens"],
                "task_time": best["task_time"].isoformat() if best["task_time"] else None,
                "file_timestamp": best.get("file_timestamp"),
            },
            "candidate_count": len(candidates),
            "candidates": [source_summary(candidate) for candidate in sorted(candidates, key=task_sort_key, reverse=True)],
        }
        aggregated_tasks.append(chosen_task)
        provenance.append(
            {
                "task_id": task_id,
                "selected_from": best["source_file"],
                "selected_run_id": best.get("source_run_id"),
                "selection_reason": copy.deepcopy(chosen_task["_aggregation"]["selection_reason"]),
                "candidates": chosen_task["_aggregation"]["candidates"],
            }
        )

    status_counter = Counter(task.get("status", "unknown") for task in aggregated_tasks)

    return {
        "aggregation_metadata": {
            "created_at": datetime.now().astimezone().isoformat(),
            "input_dir": input_dir,
            "source_file_count": len(files),
            "source_files": runs,
            "selection_policy": [
                "Prefer successful task results over non-successful ones.",
                "If success ties, prefer task results that contain token usage.",
                "If still tied, prefer the newer task-level attempt time.",
                "If still tied, prefer the newer file timestamp.",
                "If still tied, prefer lexicographically later source filename.",
                "The selected task record is preserved whole, including attempts, verifier, error, trace, and paths.",
            ],
            "aggregated_task_count": len(aggregated_tasks),
            "status_counts": dict(sorted(status_counter.items())),
        },
        "tasks": aggregated_tasks,
        "task_provenance": provenance,
    }


def main() -> None:
    args = parse_args()
    aggregated = aggregate(args.input_dir)
    ensure_parent_dir(args.output)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(aggregated, f, ensure_ascii=False, indent=args.indent)
        f.write("\n")
    print(f"Wrote aggregated results to {args.output}")
    print(f"Aggregated tasks: {aggregated['aggregation_metadata']['aggregated_task_count']}")


if __name__ == "__main__":
    main()
