#!/usr/bin/env python3
"""Compare baseline and reuse-augmented benchmark result JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def summarize_result(payload: dict[str, Any]) -> dict[str, Any]:
    tasks = payload.get("tasks", [])
    if not tasks:
        raise ValueError("Result JSON does not contain any tasks.")
    task = tasks[0]
    grading = task.get("grading", {})
    usage = task.get("usage", {})
    summary = {
        "task_id": task.get("task_id"),
        "status": task.get("status"),
        "score": grading.get("score"),
        "attempt_count": task.get("attempt_count"),
        "first_success_attempt": task.get("first_success_attempt"),
        "execution_time": task.get("execution_time"),
        "request_count": usage.get("request_count"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_tokens": usage.get("cache_read_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    return summary


def compare(baseline: dict[str, Any], reuse: dict[str, Any]) -> dict[str, Any]:
    numeric_keys = [
        "score",
        "attempt_count",
        "first_success_attempt",
        "execution_time",
        "request_count",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "total_tokens",
    ]
    deltas: dict[str, Any] = {}
    for key in numeric_keys:
        left = baseline.get(key)
        right = reuse.get(key)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            deltas[key] = right - left
        else:
            deltas[key] = None
    return {
        "baseline": baseline,
        "reuse": reuse,
        "delta_reuse_minus_baseline": deltas,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare one baseline result JSON and one reuse result JSON.")
    parser.add_argument("--baseline", required=True, help="Path to the baseline result JSON.")
    parser.add_argument("--reuse", required=True, help="Path to the reuse result JSON.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the output JSON.")
    args = parser.parse_args()

    baseline_summary = summarize_result(load_json(args.baseline))
    reuse_summary = summarize_result(load_json(args.reuse))
    output = compare(baseline_summary, reuse_summary)
    if args.pretty:
        print(json.dumps(output, indent=2, ensure_ascii=True))
    else:
        print(json.dumps(output, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
