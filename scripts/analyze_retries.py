#!/usr/bin/env python3
"""
Analyze retry benchmark results and generate success/cost curves.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "matplotlib>=3.8",
# ]
# ///

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze PinchBench retry results")
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Result JSON files. Defaults to all results/*.json files.",
    )
    parser.add_argument(
        "--output-dir",
        default="analysis/retries",
        help="Directory to write charts and summary JSON",
    )
    parser.add_argument(
        "--label-mode",
        choices=("file", "run", "policy"),
        default="file",
        help="How to label each result series in charts",
    )
    return parser.parse_args()


def _resolve_inputs(raw_inputs: List[str]) -> List[Path]:
    if raw_inputs:
        paths = [Path(item) for item in raw_inputs]
    else:
        paths = sorted(Path("results").glob("*.json"))
    return [path for path in paths if path.exists()]


def _attempt_passed(attempt: Dict[str, Any]) -> bool:
    grading = attempt.get("grading", {})
    score = float(grading.get("score", 0.0) or 0.0)
    max_score = float(grading.get("max_score", 0.0) or 0.0)
    return max_score > 0 and score >= max_score


def _attempt_usage(attempt: Dict[str, Any]) -> Dict[str, float]:
    usage = attempt.get("execution", {}).get("usage", {})
    return {
        "total_tokens": float(usage.get("total_tokens", 0) or 0.0),
        "cost_usd": float(usage.get("cost_usd", 0.0) or 0.0),
        "execution_time": float(attempt.get("execution", {}).get("execution_time", 0.0) or 0.0),
    }


def _series_label(result: Dict[str, Any], path: Path, mode: str) -> str:
    if mode == "run":
        return f"{result.get('run_id', path.stem)} | {result.get('model', 'unknown')}"
    if mode == "policy":
        retry = result.get("retry_policies", {})
        parts = [
            result.get("model", "unknown"),
            retry.get("feedback_policy", "na"),
            retry.get("feedback_format", "na"),
            retry.get("stop_rule", "na"),
            f"k={result.get('max_task_attempts', 'na')}",
        ]
        stop_threshold = retry.get("stop_threshold")
        if stop_threshold not in (None, "", 0, 0.0, "0", "0.0"):
            parts.append(f"thr={stop_threshold}")
        return " | ".join(str(part) for part in parts)
    return path.stem


def _compute_curve(result: Dict[str, Any]) -> Dict[str, Any]:
    tasks = result.get("tasks", [])
    if not tasks:
        return {
            "num_tasks": 0,
            "max_k": 0,
            "points": [],
        }

    max_k = max(len(task.get("attempts", [])) for task in tasks)
    points: List[Dict[str, Any]] = []
    num_tasks = len(tasks)

    for k in range(1, max_k + 1):
        successes = 0
        total_tokens = 0.0
        total_cost = 0.0
        total_time = 0.0

        for task in tasks:
            attempts = task.get("attempts", [])[:k]
            task_passed = False
            task_tokens = 0.0
            task_cost = 0.0
            task_time = 0.0

            for attempt in attempts:
                usage = _attempt_usage(attempt)
                task_tokens += usage["total_tokens"]
                task_cost += usage["cost_usd"]
                task_time += usage["execution_time"]
                if _attempt_passed(attempt):
                    task_passed = True

            if task_passed:
                successes += 1
            total_tokens += task_tokens
            total_cost += task_cost
            total_time += task_time

        points.append(
            {
                "k": k,
                "success_rate": round(successes / num_tasks, 6),
                "successful_tasks": successes,
                "avg_tokens_per_task": round(total_tokens / num_tasks, 3),
                "avg_cost_usd_per_task": round(total_cost / num_tasks, 6),
                "avg_execution_time_seconds_per_task": round(total_time / num_tasks, 6),
            }
        )

    previous_success_rate = 0.0
    previous_avg_tokens = 0.0
    for point in points:
        delta_success = point["success_rate"] - previous_success_rate
        delta_tokens = point["avg_tokens_per_task"] - previous_avg_tokens
        point["delta_success_rate"] = round(delta_success, 6)
        point["delta_tokens_per_task"] = round(delta_tokens, 3)
        point["success_per_1k_tokens"] = (
            round(point["success_rate"] / (point["avg_tokens_per_task"] / 1000.0), 6)
            if point["avg_tokens_per_task"] > 0
            else None
        )
        point["success_per_dollar"] = (
            round(point["success_rate"] / point["avg_cost_usd_per_task"], 6)
            if point["avg_cost_usd_per_task"] > 0
            else None
        )
        point["tokens_per_1pct_success"] = (
            round(delta_tokens / (delta_success * 100.0), 3)
            if delta_success > 0
            else None
        )
        previous_success_rate = point["success_rate"]
        previous_avg_tokens = point["avg_tokens_per_task"]

    return {
        "num_tasks": num_tasks,
        "max_k": max_k,
        "points": points,
    }


def _plot_success_at_k(series: List[Dict[str, Any]], output_dir: Path) -> None:
    plt.figure(figsize=(8, 5))
    for item in series:
        xs = [point["k"] for point in item["curve"]["points"]]
        ys = [point["success_rate"] for point in item["curve"]["points"]]
        plt.plot(xs, ys, marker="o", label=item["label"])
    plt.xlabel("Attempt Budget (k)")
    plt.ylabel("Success@k")
    plt.title("PinchBench Retry Success@k")
    plt.ylim(0, 1.05)
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(output_dir / "success_at_k.png", dpi=200)
    plt.close()


def _plot_token_cost_curve(
    series: List[Dict[str, Any]],
    output_dir: Path,
    x_field: str,
    filename: str,
    xlabel: str,
) -> None:
    plt.figure(figsize=(8, 5))
    for item in series:
        xs = [point[x_field] for point in item["curve"]["points"]]
        ys = [point["success_rate"] for point in item["curve"]["points"]]
        plt.plot(xs, ys, marker="o", label=item["label"])
    plt.xlabel(xlabel)
    plt.ylabel("Success Rate")
    plt.title(f"PinchBench Retry {xlabel} Tradeoff")
    plt.ylim(0, 1.05)
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(output_dir / filename, dpi=200)
    plt.close()


def main() -> None:
    args = _parse_args()
    input_paths = _resolve_inputs(args.inputs)
    if not input_paths:
        raise SystemExit("No result JSON files found.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    series: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {"series": []}

    for path in input_paths:
        with path.open("r", encoding="utf-8") as handle:
            result = json.load(handle)
        curve = _compute_curve(result)
        label = _series_label(result, path, args.label_mode)
        retry = result.get("retry_policies", {})
        record = {
            "file": str(path),
            "label": label,
            "model": result.get("model"),
            "run_id": result.get("run_id"),
            "suite": result.get("suite"),
            "runs_per_task": result.get("runs_per_task"),
            "max_task_attempts": result.get("max_task_attempts"),
            "retry_policies": retry,
            "curve": curve,
        }
        series.append(record)
        summary["series"].append(record)

    _plot_success_at_k(series, output_dir)
    _plot_token_cost_curve(
        series,
        output_dir,
        x_field="avg_tokens_per_task",
        filename="token_cost_curve.png",
        xlabel="Average Tokens per Task",
    )
    _plot_token_cost_curve(
        series,
        output_dir,
        x_field="avg_cost_usd_per_task",
        filename="usd_cost_curve.png",
        xlabel="Average Cost per Task (USD)",
    )

    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
