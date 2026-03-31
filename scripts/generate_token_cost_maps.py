#!/usr/bin/env python3
"""
Generate heuristic token cost maps for every task in a benchmark run.
"""
# /// script
# requires-python = ">=3.10"
# ///

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


READ_COMMANDS = {
    "ls",
    "find",
    "rg",
    "grep",
    "cat",
    "sed",
    "head",
    "tail",
    "pwd",
    "wc",
    "stat",
    "file",
    "sort",
    "env",
    "which",
    "command",
    "git",
}

WRITE_HINTS = (
    "apply_patch",
    "patch",
    "tee ",
    ">",
    ">>",
    "mkdir ",
    "touch ",
    "cp ",
    "mv ",
    "chmod ",
    "python -c",
    "python3 -c",
    "printf ",
    "echo ",
)

TOOL_FAILURE_HINTS = (
    "error",
    "failed",
    "gateway",
    "closed connection",
    "timed out",
    "timeout",
    "not found",
    "permission denied",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate heuristic token cost maps.")
    parser.add_argument("input", help="Benchmark run JSON file")
    parser.add_argument(
        "--output-dir",
        default="results/token_cost_maps",
        help="Directory where per-task token cost map JSON files will be written",
    )
    return parser.parse_args()


def sanitize_stem(task_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", task_id)


def round4(value: float) -> float:
    return round(float(value), 4)


def short_text(value: str | None, limit: int = 220) -> str:
    if not value:
        return ""
    value = " ".join(str(value).split())
    return value[: limit - 3] + "..." if len(value) > limit else value


def attempt_passed(attempt: dict[str, Any]) -> bool:
    completion = attempt.get("completion", {}) or {}
    if "passed" in completion:
        return bool(completion.get("passed"))
    grading = attempt.get("grading", {}) or {}
    score = float(grading.get("score", 0.0) or 0.0)
    max_score = float(grading.get("max_score", 0.0) or 0.0)
    return max_score > 0 and score >= max_score


def extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    items = message.get("content") or []
    return [item for item in items if item.get("type") == "toolCall"]


def extract_text_items(message: dict[str, Any]) -> list[str]:
    items = message.get("content") or []
    result = []
    for item in items:
        if item.get("type") == "text":
            text = item.get("text")
            if text:
                result.append(text)
    return result


def command_words(command: str) -> list[str]:
    command = command.strip()
    if not command:
        return []
    return re.findall(r"[A-Za-z0-9_.:/-]+", command)


def classify_round(
    command_text: str,
    assistant_text: str,
    attempt_index: int,
    within_attempt_round: int,
    score_delta: float,
    final_attempt: bool,
) -> tuple[str, str, str, str]:
    lower_command = command_text.lower()
    lower_text = assistant_text.lower()
    words = command_words(lower_command)
    first_word = words[0] if words else ""

    has_write = any(hint in lower_command for hint in WRITE_HINTS)
    has_read = first_word in READ_COMMANDS or any(f" {cmd} " in f" {lower_command} " for cmd in READ_COMMANDS)
    has_failure = any(hint in lower_text or hint in lower_command for hint in TOOL_FAILURE_HINTS)
    final_answer_like = not command_text and bool(assistant_text.strip())

    if has_failure:
        return (
            "exploration",
            "tool_failure",
            "wasteful",
            "Tooling or infrastructure failure consumed budget without advancing the task.",
        )

    if final_answer_like and final_attempt and within_attempt_round == 1:
        return (
            "generation",
            "none",
            "necessary",
            "Cheap final answer step.",
        )

    if has_write:
        if attempt_index == 1:
            return (
                "generation",
                "none",
                "necessary" if score_delta >= 0 else "overpriced",
                "Task work produced or modified artifacts directly.",
            )
        return (
            "repair",
            "none",
            "necessary" if score_delta > 0 else "overpriced",
            "Retry focused on changing artifacts or state.",
        )

    if has_read and attempt_index == 1 and within_attempt_round <= 2:
        return (
            "exploration",
            "misselection",
            "overpriced",
            "Early read-only probing before direct task execution.",
        )

    if has_read and score_delta > 0:
        return (
            "verification",
            "none",
            "necessary",
            "Read-only action helped verify or localize progress.",
        )

    if has_read and attempt_index > 1:
        return (
            "verification",
            "misselection",
            "overpriced",
            "Read-only checking consumed budget without clearing the remaining bottleneck.",
        )

    if final_answer_like and score_delta > 0:
        return (
            "generation",
            "none",
            "necessary",
            "Direct answer contributed to task progress.",
        )

    if final_answer_like:
        return (
            "generation",
            "redundant_retry",
            "overpriced",
            "Answering step did not change the judged outcome.",
        )

    if attempt_index == 1:
        return (
            "acquisition",
            "none",
            "necessary",
            "General task-state acquisition step.",
        )

    return (
        "verification",
        "redundant_retry",
        "overpriced",
        "Retry action had limited measurable impact.",
    )


def summarize_attempt_notes(attempt: dict[str, Any]) -> str:
    notes = attempt.get("grading", {}).get("notes")
    if notes:
        return short_text(notes, 300)
    feedback_stats = attempt.get("feedback_prompt_stats") or {}
    if feedback_stats.get("unresolved_criteria_count") is not None:
        count = feedback_stats["unresolved_criteria_count"]
        return f"Attempt ended with {count} unresolved criteria."
    return "No detailed grading note available."


def attempt_newly_resolved(prev_breakdown: dict[str, Any], curr_breakdown: dict[str, Any]) -> list[str]:
    resolved = []
    for key, value in curr_breakdown.items():
        prev_value = float(prev_breakdown.get(key, 0.0) or 0.0)
        curr_value = float(value or 0.0)
        if curr_value > prev_value:
            resolved.append(key)
    return resolved


def remaining_bottleneck(curr_breakdown: dict[str, Any]) -> str:
    unresolved = [key for key, value in curr_breakdown.items() if float(value or 0.0) < 1.0]
    if not unresolved:
        return "No unresolved criterion remained."
    return unresolved[0]


def build_round_records(task: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    global_round = 0
    prev_score = 0.0
    total_attempts = len(task.get("attempts", []))

    for attempt in task.get("attempts", []):
        execution = attempt.get("execution", {})
        transcript = execution.get("transcript", [])
        assistant_messages = [
            item["message"]
            for item in transcript
            if item.get("type") == "message" and item.get("message", {}).get("role") == "assistant"
        ]
        usage_per_round = execution.get("usage_per_round", [])
        count = min(len(assistant_messages), len(usage_per_round))
        curr_score = float(attempt.get("grading", {}).get("score", 0.0) or 0.0)
        score_delta = curr_score - prev_score

        for idx in range(count):
            global_round += 1
            msg = assistant_messages[idx]
            usage = usage_per_round[idx]
            tool_calls = extract_tool_calls(msg)
            command_text = " | ".join(
                str(call.get("arguments", {}).get("command", "")) for call in tool_calls
            ).strip()
            assistant_text = " ".join(extract_text_items(msg))
            primary, secondary, status, generic_note = classify_round(
                command_text=command_text,
                assistant_text=assistant_text,
                attempt_index=int(attempt.get("attempt", 0) or 0),
                within_attempt_round=idx + 1,
                score_delta=score_delta,
                final_attempt=int(attempt.get("attempt", 0) or 0) == total_attempts,
            )
            evidence = command_text or short_text(assistant_text, 180) or "Heuristic classification from transcript usage."
            records.append(
                {
                    "attempt": int(attempt.get("attempt", 0) or 0),
                    "within_attempt_round": idx + 1,
                    "round": global_round,
                    "primary_label": primary,
                    "secondary_label": secondary,
                    "status": status,
                    "input_tokens": int(usage.get("input_tokens", 0) or 0),
                    "cache_input_tokens": None,
                    "output_tokens": int(usage.get("output_tokens", 0) or 0),
                    "note": generic_note,
                    "evidence": short_text(evidence, 260),
                }
            )

        prev_score = curr_score

    return records


def build_attempt_records(task: dict[str, Any], round_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attempts_out = []
    prev_breakdown: dict[str, Any] = {}

    for attempt in task.get("attempts", []):
        attempt_id = int(attempt.get("attempt", 0) or 0)
        execution = attempt.get("execution", {})
        grading = attempt.get("grading", {})
        usage = execution.get("usage", {})
        breakdown = grading.get("breakdown", {}) or {}
        attempt_rounds = [item for item in round_records if item["attempt"] == attempt_id]
        cost_breakdown = {
            "necessary_input_tokens": sum(r["input_tokens"] for r in attempt_rounds if r["status"] == "necessary"),
            "overpriced_input_tokens": sum(r["input_tokens"] for r in attempt_rounds if r["status"] == "overpriced"),
            "wasteful_input_tokens": sum(r["input_tokens"] for r in attempt_rounds if r["status"] == "wasteful"),
        }
        attempts_out.append(
            {
                "attempt": attempt_id,
                "status": execution.get("status", "unknown"),
                "score": float(grading.get("score", 0.0) or 0.0),
                "passed": attempt_passed(attempt),
                "input_tokens": int(usage.get("input_tokens", 0) or 0),
                "output_tokens": int(usage.get("output_tokens", 0) or 0),
                "cache_input_tokens": int(usage.get("cache_read_tokens", 0) or 0),
                "request_count": int(usage.get("request_count", 0) or 0),
                "newly_resolved_criteria": attempt_newly_resolved(prev_breakdown, breakdown),
                "remaining_bottleneck": remaining_bottleneck(breakdown),
                "cost_breakdown": cost_breakdown,
                "notes": summarize_attempt_notes(attempt),
            }
        )
        prev_breakdown = breakdown

    return attempts_out


def build_task_summary(task: dict[str, Any], round_records: list[dict[str, Any]]) -> dict[str, Any]:
    total_input = int(task.get("usage", {}).get("input_tokens", 0) or 0)
    total_output = int(task.get("usage", {}).get("output_tokens", 0) or 0)
    total_cache = int(task.get("usage", {}).get("cache_read_tokens", 0) or 0)

    if round_records:
        dominant = max(
            ("necessary", "overpriced", "wasteful"),
            key=lambda label: sum(r["input_tokens"] for r in round_records if r["status"] == label),
        )
        exemplar = next(r for r in round_records if r["status"] == dominant)
        note = {
            "necessary": "Most spend was directly tied to task completion work.",
            "overpriced": "Most spend came from real task work applied inefficiently or against the wrong bottleneck.",
            "wasteful": "Most spend came from detours that did not materially advance the task.",
        }[dominant]
        evidence = exemplar["evidence"]
        primary = exemplar["primary_label"]
        secondary = exemplar["secondary_label"]
    else:
        dominant = "necessary"
        note = "No per-round records were available."
        evidence = "No round data."
        primary = "generation"
        secondary = "none"

    return {
        "primary_label": primary,
        "secondary_label": secondary,
        "status": dominant,
        "input_tokens": total_input,
        "cache_input_tokens": total_cache,
        "output_tokens": total_output,
        "note": note,
        "evidence": evidence,
    }


def build_cost_summary(task: dict[str, Any], round_records: list[dict[str, Any]]) -> dict[str, Any]:
    usage = task.get("usage", {}) or {}
    attempts = task.get("attempts", [])
    first_usage = ((attempts[0] or {}).get("execution", {}) or {}).get("usage", {} if attempts else {})
    first_input = int(first_usage.get("input_tokens", 0) or 0)
    first_output = int(first_usage.get("output_tokens", 0) or 0)
    first_cache = int(first_usage.get("cache_read_tokens", 0) or 0)
    total_input = int(usage.get("input_tokens", 0) or 0)
    total_output = int(usage.get("output_tokens", 0) or 0)
    total_cache = int(usage.get("cache_read_tokens", 0) or 0)

    necessary_input = sum(r["input_tokens"] for r in round_records if r["status"] == "necessary")
    necessary_output = sum(r["output_tokens"] for r in round_records if r["status"] == "necessary")
    overpriced_input = sum(r["input_tokens"] for r in round_records if r["status"] == "overpriced")
    overpriced_output = sum(r["output_tokens"] for r in round_records if r["status"] == "overpriced")
    wasteful_input = sum(r["input_tokens"] for r in round_records if r["status"] == "wasteful")
    wasteful_output = sum(r["output_tokens"] for r in round_records if r["status"] == "wasteful")

    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cache_input_tokens": total_cache,
        "total_cost_usd": float(usage.get("cost_usd", 0.0) or 0.0),
        "request_count": int(usage.get("request_count", 0) or 0),
        "first_attempt_cost": {
            "input_tokens": first_input,
            "output_tokens": first_output,
            "cache_input_tokens": first_cache,
            "share_of_total_input": round4(first_input / total_input) if total_input else 0.0,
        },
        "retry_cost": {
            "input_tokens": total_input - first_input,
            "output_tokens": total_output - first_output,
            "cache_input_tokens": total_cache - first_cache,
            "share_of_total_input": round4((total_input - first_input) / total_input) if total_input else 0.0,
        },
        "necessity_split": {
            "necessary": {
                "input_tokens": necessary_input,
                "output_tokens": necessary_output,
                "share_of_total_input": round4(necessary_input / total_input) if total_input else 0.0,
            },
            "overpriced": {
                "input_tokens": overpriced_input,
                "output_tokens": overpriced_output,
                "share_of_total_input": round4(overpriced_input / total_input) if total_input else 0.0,
            },
            "wasteful": {
                "input_tokens": wasteful_input,
                "output_tokens": wasteful_output,
                "share_of_total_input": round4(wasteful_input / total_input) if total_input else 0.0,
            },
        },
        "inefficiency_summary": {
            "intra_attempt_inefficiency_input_tokens": overpriced_input + wasteful_input,
            "inter_attempt_retry_input_tokens": total_input - first_input,
            "interpretation": "Heuristic split between directly useful work and inefficient spend inferred from transcript behavior.",
        },
    }


def build_task_outcome(task: dict[str, Any]) -> dict[str, Any]:
    attempts = task.get("attempts", [])
    first_success_attempt = None
    for attempt in attempts:
        if attempt_passed(attempt):
            first_success_attempt = int(attempt.get("attempt", 0) or 0)
            break

    final_breakdown = task.get("grading", {}).get("breakdown", {}) or {}
    unresolved = [key for key, value in final_breakdown.items() if float(value or 0.0) < 1.0]

    return {
        "final_success": bool(task.get("completion", {}).get("passed", False)),
        "final_score": float(task.get("grading", {}).get("score", 0.0) or 0.0),
        "max_score": float(task.get("grading", {}).get("max_score", 0.0) or 0.0),
        "first_attempt_success": bool(attempts and attempt_passed(attempts[0])),
        "first_success_attempt": first_success_attempt,
        "max_task_attempts": int(task.get("max_task_attempts", len(attempts)) or len(attempts)),
        "attempts_executed": len(attempts),
        "dominant_failure": unresolved[0] if unresolved else None,
        "final_unresolved_criteria": unresolved,
        "final_notes": short_text(task.get("grading", {}).get("notes", ""), 320),
    }


def build_map(result: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    round_records = build_round_records(task)
    attempts_out = build_attempt_records(task, round_records)
    return {
        "task_id": task.get("task_id"),
        "task_name": task.get("frontmatter", {}).get("name", task.get("task_id")),
        "source_run": result.get("_source_path"),
        "model": result.get("model"),
        "analysis_method": "heuristic",
        "analysis_note": "Labels and necessity assessments are generated from attempt structure, transcript tool usage, and score deltas. They are suitable for batch comparison, not as a substitute for manual task-specific annotation.",
        "schema": {
            "attempts": "Per-attempt trajectory with score, unresolved bottleneck, token usage, and cost decomposition.",
            "round_labels": "Per-round labeling with attempt index, within-attempt round index, lifecycle stage, mechanism label, and necessity assessment.",
            "cost_summary": "Top-level aggregates for first-attempt cost, retry cost, and token inefficiency splits.",
        },
        "task_outcome": build_task_outcome(task),
        "cost_summary": build_cost_summary(task, round_records),
        "task_summary": build_task_summary(task, round_records),
        "attempts": attempts_out,
        "round_labels": round_records,
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8") as handle:
        result = json.load(handle)
    result["_source_path"] = str(input_path.resolve())

    for task in result.get("tasks", []):
        token_map = build_map(result, task)
        output_path = output_dir / f"{sanitize_stem(task['task_id'])}_token_cost_map.json"
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(token_map, handle, indent=2, ensure_ascii=False)
            handle.write("\n")

    manifest = {
        "source_run": str(input_path.resolve()),
        "model": result.get("model"),
        "run_id": result.get("run_id"),
        "task_count": len(result.get("tasks", [])),
        "output_dir": str(output_dir.resolve()),
        "files": sorted(path.name for path in output_dir.glob("*_token_cost_map.json")),
    }
    with (output_dir / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


if __name__ == "__main__":
    main()
