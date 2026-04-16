#!/usr/bin/env python3
"""
PinchBench - OpenClaw Agent Benchmarking System

This script orchestrates benchmarking of OpenClaw agents using tasks loaded
from the tasks/ directory.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pyyaml>=6.0.1",
# ]
# ///

import argparse
import json
import logging
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

from lib_agent import _run_openclaw_message, cleanup_agent_sessions, ensure_agent_exists, execute_openclaw_task, slugify_model
from early_stop_policy import decide_inter_attempt_stop
from lib_grading import (
    GradeResult,
    KIMI_JUDGE_API_BASE,
    KIMI_JUDGE_MODEL,
    grade_task,
    load_default_judge_api_key,
)
from lib_tasks import Task, TaskLoader


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("benchmark.log")],
)

logger = logging.getLogger("benchmark")
TASK_SPECIFIC_REPAIR_STEPS_PATH = (
    Path(__file__).resolve().parent.parent / "analysis" / "task_specific_repair_steps.json"
)
_TASK_SPECIFIC_REPAIR_STEPS_CACHE: Optional[Dict[str, Any]] = None
QUOTA_LIMIT_EXIT_CODE = 3


class OpenClawAgent:
    """Scaffold for OpenClaw agent creation and execution."""

    def __init__(self, agent_id: str, config: Optional[Dict[str, Any]] = None):
        self.agent_id = agent_id
        self.config = config or {}
        logger.info(f"Initialized OpenClawAgent: {agent_id}")

    def execute_task(self, task: Task, simulate: bool = False) -> Dict[str, Any]:
        """
        Execute a task with this agent.

        Args:
            task: The Task object to execute
            simulate: If True, simulates execution for demonstration

        Returns:
            Dictionary containing execution results
        """
        if simulate:
            logger.info("Simulate flag no longer supported for execute_task")
        raise NotImplementedError("Use execute_openclaw_task helper for real runs")


class BenchmarkRunner:
    """Orchestrates benchmark execution across tasks and agents."""

    def __init__(self, tasks_dir: Path):
        self.task_loader = TaskLoader(tasks_dir)
        self.tasks: List[Task] = []
        self.agents: List[OpenClawAgent] = []
        logger.info("Initialized BenchmarkRunner")

    def load_tasks(self) -> None:
        """Load all tasks from the tasks directory."""
        logger.info("Loading tasks...")
        self.tasks = self.task_loader.load_all_tasks()
        logger.info(f"Loaded {len(self.tasks)} tasks")

    def create_agent(self, agent_id: str, config: Optional[Dict[str, Any]] = None) -> OpenClawAgent:
        """
        Create a new OpenClaw agent for benchmarking.

        Args:
            agent_id: Unique identifier for the agent
            config: Optional configuration dictionary

        Returns:
            OpenClawAgent instance
        """
        logger.info(f"Creating agent: {agent_id}")
        agent = OpenClawAgent(agent_id, config)
        self.agents.append(agent)
        return agent

    def run_benchmark(
        self, agent: OpenClawAgent, task_ids: Optional[List[str]] = None, simulate: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Run benchmark for an agent on specified tasks.

        Args:
            agent: The OpenClawAgent to benchmark
            task_ids: Optional list of task IDs to run. If None, runs all tasks.
            simulate: If True, simulates execution for demonstration

        Returns:
            List of result dictionaries
        """
        # Filter tasks if specific IDs provided
        if task_ids:
            tasks_to_run = [t for t in self.tasks if t.task_id in task_ids]
            logger.info(f"🎯 Running benchmark on {len(tasks_to_run)} specified tasks")
        else:
            tasks_to_run = self.tasks
            logger.info(f"🎯 Running benchmark on all {len(tasks_to_run)} tasks")

        results = []
        for i, task in enumerate(tasks_to_run, 1):
            logger.info(f"\n{'=' * 80}")
            logger.info(f"📋 Task {i}/{len(tasks_to_run)}")
            logger.info(f"{'=' * 80}")
            result = agent.execute_task(task, simulate=simulate)
            results.append(result)

        logger.info(f"\n{'=' * 80}")
        logger.info(f"✨ Benchmark complete! Executed {len(results)} tasks")
        logger.info(f"{'=' * 80}")

        # Print summary
        total_time = sum(r["execution_time"] for r in results)
        logger.info(f"\n📊 BENCHMARK SUMMARY")
        logger.info(f"   Agent: {agent.agent_id}")
        logger.info(f"   Tasks completed: {len(results)}")
        logger.info(f"   Total execution time: {total_time:.2f}s")
        logger.info(f"   Average time per task: {total_time / len(results):.2f}s")

        return results

    def print_task_summary(self) -> None:
        """Print a summary of all loaded tasks."""
        if not self.tasks:
            logger.warning("No tasks loaded")
            return

        print("\n" + "=" * 80)
        print(f"LOADED TASKS SUMMARY ({len(self.tasks)} tasks)")
        print("=" * 80)

        for task in self.tasks:
            print(f"\n[{task.task_id}] {task.name}")
            print(f"  Category: {task.category}")
            print(f"  Grading: {task.grading_type}")
            print(f"  Timeout: {task.timeout_seconds}s")
            print(f"  Criteria: {len(task.grading_criteria)} items")
            print(
                f"  Prompt: {task.prompt[:100]}..."
                if len(task.prompt) > 100
                else f"  Prompt: {task.prompt}"
            )

        print("\n" + "=" * 80)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PinchBench OpenClaw Benchmark Runner")
    parser.add_argument(
        "--model",
        required=False,
        help="Model identifier (e.g., anthropic/claude-sonnet-4)",
    )
    parser.add_argument(
        "--suite",
        default="all",
        help='Tasks to run: "all", "automated-only", or comma-separated IDs',
    )
    parser.add_argument(
        "--output-dir",
        default="results",
        help="Results directory",
    )
    parser.add_argument(
        "--register",
        action="store_true",
        help="Request a new API token and save it to local config",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip uploading to server",
    )
    parser.add_argument(
        "--upload",
        type=str,
        metavar="RESULTS_JSON",
        help="Upload a previous run's results JSON and exit (skips benchmarking)",
    )
    parser.add_argument(
        "--timeout-multiplier",
        type=float,
        default=1.0,
        help="Scale all task timeouts",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of runs per task for averaging",
    )
    parser.add_argument(
        "--max-task-attempts",
        type=int,
        default=1,
        help="Maximum validator-feedback iterations per task run",
    )
    parser.add_argument(
        "--feedback-policy",
        choices=(
            "vague",
            "error-localized",
            "actionable-path",
            "actionable-path-file",
        ),
        default="error-localized",
        help="Retry feedback content policy",
    )
    parser.add_argument(
        "--feedback-format",
        choices=("full-refresh", "stable-prefix"),
        default="stable-prefix",
        help="Retry feedback formatting policy (default: cache-friendly stable-prefix)",
    )
    parser.add_argument(
        "--feedback-answer-safety",
        choices=("permissive", "no-answers"),
        default="no-answers",
        help="Hide validator details that may reveal expected answers in retry feedback.",
    )
    parser.add_argument(
        "--stop-rule",
        choices=(
            "max-attempts-only",
            "no-improvement",
            "score-stall",
            "unresolved-stall",
            "low-return",
            "verifier-narrowing",
        ),
        default="max-attempts-only",
        help="Rule for stopping validator-feedback retries",
    )
    parser.add_argument(
        "--stop-threshold",
        type=float,
        default=0.0,
        help="Threshold used by some stop rules (e.g. low-return or score-stall)",
    )
    parser.add_argument(
        "--judge",
        default=None,
        help="Judge model identifier (default: openrouter/anthropic/claude-opus-4.5)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging (shows transcript contents, workspace files, etc.)",
    )
    parser.add_argument(
        "--official-key",
        type=str,
        metavar="KEY",
        help="Official key to mark submission as official (can also use PINCHBENCH_OFFICIAL_KEY env var)",
    )
    parser.add_argument(
        "--judge-api-base",
        type=str,
        default=KIMI_JUDGE_API_BASE,
        help="LLM judge API base URL (default: https://www.autodl.art/api/v1).",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default=KIMI_JUDGE_MODEL,
        help="LLM judge model name (default: Kimi-K2.5).",
    )
    parser.add_argument(
        "--judge-api-key",
        type=str,
        default=None,
        help="LLM judge API key. Defaults to env PINCHBENCH_KIMI_JUDGE_API_KEY, AUTODL_API_KEY, /root/autodlAPIKEY, or /hy-tmp/.autodlapikey.",
    )
    return parser.parse_args()


def _select_task_ids(tasks: List[Task], suite: str) -> Optional[List[str]]:
    if suite == "all":
        return None
    if suite == "automated-only":
        return [task.task_id for task in tasks if task.grading_type == "automated"]
    return [task_id.strip() for task_id in suite.split(",") if task_id.strip()]


def _next_run_id(run_root: Path) -> str:
    run_root.mkdir(parents=True, exist_ok=True)
    existing = []
    for entry in run_root.iterdir():
        if entry.is_dir() and entry.name.isdigit():
            existing.append(int(entry.name))
    next_id = (max(existing) + 1) if existing else 1
    return f"{next_id:04d}"


def _load_ascii_art(script_dir: Path, filename: str) -> str | None:
    """Load ASCII art from a local file if available."""
    art_path = script_dir / filename
    try:
        return art_path.read_text(encoding="utf-8").rstrip("\n")
    except FileNotFoundError:
        return None


def _supports_truecolor() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _get_git_version(script_dir: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
            cwd=script_dir,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _colorize_gradient(ascii_art: str) -> str:
    if not _supports_truecolor():
        return ascii_art
    lines = ascii_art.splitlines()
    if not lines:
        return ascii_art
    last_index = max(len(lines) - 1, 1)
    colored_lines = []
    for idx, line in enumerate(lines):
        t = idx / last_index
        green_blue = int(255 * (1 - t))
        colored_lines.append(f"\x1b[38;2;255;{green_blue};{green_blue}m{line}\x1b[0m")
    return "\n".join(colored_lines)


def _completion_summary(grading: Dict[str, Any]) -> Dict[str, Any]:
    """Build task completion summary from grading dict."""
    runs = grading.get("runs", [])
    mean = float(grading.get("mean", 0.0))
    max_score = 1.0
    notes = ""
    if runs:
        max_score = float(runs[0].get("max_score", 1.0))
        notes = runs[0].get("notes", "")
    return {
        "score": round(mean, 4),
        "max_score": max_score,
        "passed": mean >= max_score if max_score > 0 else False,
        "notes": notes,
    }


def _grade_passed(grade: GradeResult) -> bool:
    return grade.max_score > 0 and grade.score >= grade.max_score


def _format_breakdown_lines(grade: GradeResult, unresolved_only: bool = False) -> List[str]:
    lines = []
    for key, value in grade.breakdown.items():
        if unresolved_only and value >= 1.0:
            continue
        lines.append(f"- {key}: {value:.4f}")
    if not lines:
        if unresolved_only:
            return ["- No unresolved breakdown items were reported."]
        return ["- No detailed breakdown available from the validator."]
    return lines


def _safe_validator_notes(grade: GradeResult, *, answer_safety: str) -> str:
    if answer_safety != "no-answers":
        return grade.notes.strip() if grade.notes else "No additional validator notes."

    unresolved_count = _unresolved_criteria_count(grade)
    if unresolved_count <= 0:
        return "Validator passed with no remaining issues."
    return (
        "Validator found remaining issues. Inspect the failing output artifacts and repair the "
        "smallest set of changes needed to satisfy the unresolved checks."
    )


def _safe_breakdown_lines(
    grade: GradeResult,
    *,
    unresolved_only: bool = False,
    answer_safety: str,
) -> List[str]:
    if answer_safety != "no-answers":
        return _format_breakdown_lines(grade, unresolved_only=unresolved_only)

    unresolved_keys = [key for key, value in grade.breakdown.items() if value < 1.0]
    if unresolved_only:
        if not unresolved_keys:
            return ["- There are no unresolved validator criteria."]
        return [f"- Unresolved validator criterion: {key}" for key in unresolved_keys[:8]]

    lines = [
        f"- Total validator criteria: {len(grade.breakdown)}",
        f"- Unresolved validator criteria: {len(unresolved_keys)}",
    ]
    lines.extend(f"- Unresolved validator criterion: {key}" for key in unresolved_keys[:8])
    return lines


def _load_task_specific_repair_steps() -> Dict[str, Any]:
    global _TASK_SPECIFIC_REPAIR_STEPS_CACHE
    if _TASK_SPECIFIC_REPAIR_STEPS_CACHE is not None:
        return _TASK_SPECIFIC_REPAIR_STEPS_CACHE
    try:
        _TASK_SPECIFIC_REPAIR_STEPS_CACHE = json.loads(
            TASK_SPECIFIC_REPAIR_STEPS_PATH.read_text()
        )
    except FileNotFoundError:
        logger.warning(
            "Task-specific repair steps file not found: %s",
            TASK_SPECIFIC_REPAIR_STEPS_PATH,
        )
        _TASK_SPECIFIC_REPAIR_STEPS_CACHE = {"tasks": {}}
    except json.JSONDecodeError as exc:
        logger.warning(
            "Failed to parse task-specific repair steps file %s: %s",
            TASK_SPECIFIC_REPAIR_STEPS_PATH,
            exc,
        )
        _TASK_SPECIFIC_REPAIR_STEPS_CACHE = {"tasks": {}}
    return _TASK_SPECIFIC_REPAIR_STEPS_CACHE


_TASK_SPECIFIC_REPAIR_STEPS_CACHE = _load_task_specific_repair_steps()


def _retry_policy_instructions(feedback_policy: str) -> str:
    if feedback_policy == "vague":
        return (
            "- Continue working in the same workspace.\n"
            "- Do not restart from scratch unless necessary.\n"
            "- Make the minimal changes needed to pass validation.\n"
            "- When you are done, provide the updated final answer."
        )
    if feedback_policy in {"actionable-path", "actionable-path-file"}:
        return (
            "- Continue working in the same workspace.\n"
            "- Do not restart from scratch unless necessary.\n"
            "- Address only unresolved issues.\n"
            "- Follow the suggested repair plan, especially any task-specific steps.\n"
            "- Prefer targeted fixes over broad rewrites.\n"
            "- When you are done, provide the updated final answer."
        )
    return (
        "- Continue working in the same workspace.\n"
        "- Do not restart from scratch unless necessary.\n"
        "- Focus on unresolved issues only.\n"
        "- Do not repeat already-correct work unless required.\n"
        "- When you are done, provide the updated final answer."
    )


def _actionable_repair_steps(task: Task, grade: GradeResult) -> List[str]:
    task_specific = (
        _load_task_specific_repair_steps().get("tasks", {}).get(task.task_id)
    )
    if task_specific:
        configured_steps = task_specific.get("repair_steps") or []
        if configured_steps:
            return [
                f"{idx}. {step}"
                for idx, step in enumerate(configured_steps, start=1)
            ]

    unresolved = [key for key, value in grade.breakdown.items() if value < 1.0]
    steps = []
    if unresolved:
        steps.append(
            "1. Review the unresolved validator items and map each one to a concrete fix."
        )
    else:
        steps.append("1. Re-check the latest output against the grading criteria.")
    steps.append("2. Verify the required files, tool calls, and final answer format.")
    steps.append("3. Edit only what is needed to satisfy the remaining requirements.")
    return steps


def _interactive_actionable_enabled(feedback_policy: str) -> bool:
    return feedback_policy == "actionable-path"


def _format_actionable_effect_summary(
    *,
    current_grade: GradeResult,
    previous_attempt_summary: Optional[Dict[str, Any]],
    transcript_length_delta: Optional[int] = None,
) -> List[str]:
    lines = []
    score_delta = _score_delta(
        current_grade.score,
        None if not previous_attempt_summary else previous_attempt_summary.get("grading", {}).get("score"),
    )
    if score_delta is None:
        lines.append("- Effect vs previous attempt: baseline attempt, no comparison yet.")
    else:
        lines.append(f"- Effect vs previous attempt: score delta {score_delta:+.4f}.")
    current_unresolved = _unresolved_criteria_count(current_grade)
    if previous_attempt_summary is not None:
        previous_unresolved = int(previous_attempt_summary.get("unresolved_criteria_count", 0) or 0)
        unresolved_delta = current_unresolved - previous_unresolved
        lines.append(
            f"- Unresolved criteria: {current_unresolved} ({unresolved_delta:+d} vs previous attempt)."
        )
    else:
        lines.append(f"- Unresolved criteria: {current_unresolved}.")
    if transcript_length_delta is not None:
        lines.append(f"- Transcript growth this attempt: {transcript_length_delta:+d} turns.")
    return lines


def _read_multiline_console_input(prompt_label: str) -> str:
    print(prompt_label)
    print("(Finish with an empty line.)")
    lines: List[str] = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _collect_interactive_actionable_feedback(
    *,
    task: Task,
    attempt_number: int,
    grade: GradeResult,
    previous_attempt_summary: Optional[Dict[str, Any]],
    transcript_length_delta: Optional[int],
    answer_safety: str,
) -> Dict[str, Any]:
    if not sys.stdin.isatty():
        raise RuntimeError(
            "actionable-path now requires an interactive terminal so it can pause for human guidance."
        )

    unresolved_breakdown = "\n".join(
        _safe_breakdown_lines(
            grade,
            unresolved_only=True,
            answer_safety=answer_safety,
        )
    )
    if not unresolved_breakdown:
        unresolved_breakdown = "- No unresolved breakdown items were returned."
    notes = _safe_validator_notes(grade, answer_safety=answer_safety)
    effect_lines = _format_actionable_effect_summary(
        current_grade=grade,
        previous_attempt_summary=previous_attempt_summary,
        transcript_length_delta=transcript_length_delta,
    )

    print("\n" + "=" * 80)
    print(f"INTERACTIVE ACTIONABLE RETRY | {task.task_id} | after attempt {attempt_number}")
    print("=" * 80)
    print(f"Score: {grade.score:.4f}/{grade.max_score:.4f}")
    print("Why this attempt did not get full score:")
    print(unresolved_breakdown)
    print("\nValidator notes:")
    print(notes)
    print("\nObserved effect:")
    for line in effect_lines:
        print(line)
    print()

    next_instruction = _read_multiline_console_input(
        "Enter the next instruction for the model."
    )

    return {
        "attempt": attempt_number,
        "score": round(float(grade.score), 6),
        "max_score": round(float(grade.max_score), 6),
        "unresolved_criteria_count": _unresolved_criteria_count(grade),
        "unresolved_breakdown": unresolved_breakdown,
        "quality_record": {
            "score": round(float(grade.score), 6),
            "max_score": round(float(grade.max_score), 6),
            "unresolved_criteria_count": _unresolved_criteria_count(grade),
            "unresolved_breakdown": unresolved_breakdown,
            "validator_notes": notes,
            "effect_summary": effect_lines,
        },
        "validator_notes": notes,
        "effect_summary": effect_lines,
        "next_instruction": next_instruction,
    }


def _format_actionable_history_entry(entry: Dict[str, Any]) -> str:
    effect_summary = "\n".join(entry.get("effect_summary") or ["- No effect summary recorded."])
    next_instruction = entry.get("next_instruction") or "(none)"
    return (
        f"Attempt {entry['attempt']} review:\n"
        f"- Score: {float(entry.get('score', 0.0)):.4f}/{float(entry.get('max_score', 1.0)):.4f}\n"
        f"- Unresolved criteria count: {entry.get('unresolved_criteria_count', 0)}\n"
        "Why it did not get full score:\n"
        f"{entry.get('unresolved_breakdown', '- No unresolved issues recorded.')}\n\n"
        "Validator notes:\n"
        f"{entry.get('validator_notes', 'No validator notes.')}\n\n"
        "Observed effect:\n"
        f"{effect_summary}\n\n"
        "Quality record source: validator / judge output.\n\n"
        "Human next-step instruction:\n"
        f"{next_instruction}"
    )


def _build_iteration_feedback(
    task: Task,
    grade: GradeResult,
    attempt_number: int,
    *,
    feedback_policy: str,
    feedback_format: str,
    feedback_answer_safety: str,
) -> Dict[str, Any]:
    notes = _safe_validator_notes(grade, answer_safety=feedback_answer_safety)
    criteria = "\n".join(f"- {item}" for item in task.grading_criteria) or "- None provided."
    full_breakdown = "\n".join(
        _safe_breakdown_lines(
            grade,
            unresolved_only=False,
            answer_safety=feedback_answer_safety,
        )
    )
    unresolved_breakdown = "\n".join(
        _safe_breakdown_lines(
            grade,
            unresolved_only=True,
            answer_safety=feedback_answer_safety,
        )
    )
    unresolved_count = sum(1 for value in grade.breakdown.values() if value < 1.0)

    if feedback_format == "stable-prefix":
        stable_prefix = (
            f"You are working on benchmark task `{task.task_id}`.\n\n"
            "Task passes only when the validator score reaches the maximum.\n\n"
            "Original grading criteria:\n"
            f"{criteria}\n\n"
            "Retry policy:\n"
            f"{_retry_policy_instructions(feedback_policy)}"
        )
        dynamic_suffix = (
            f"\n\nLatest validator result:\n"
            f"- Attempt: {attempt_number}\n"
            f"- Score: {grade.score:.4f}/{grade.max_score:.4f}\n"
        )
        if feedback_policy == "vague":
            dynamic_suffix += (
                "\nThe task did not pass. Improve the result and try again."
            )
        elif feedback_policy == "error-localized":
            dynamic_suffix += (
                "\n\nRemaining issues:\n"
                f"{unresolved_breakdown}\n\n"
                "Validator notes:\n"
                f"{notes}"
            )
        else:
            dynamic_suffix += (
                "\n\nUnresolved issues:\n"
                f"{unresolved_breakdown}\n\n"
                "Suggested repair plan:\n"
                f"{chr(10).join(_actionable_repair_steps(task, grade))}\n\n"
                "Validator notes:\n"
                f"{notes}"
            )
        text = stable_prefix + dynamic_suffix
        return {
            "text": text,
            "text_length_chars": len(text),
            "stable_prefix_length_chars": len(stable_prefix),
            "dynamic_suffix_length_chars": len(dynamic_suffix),
            "unresolved_criteria_count": unresolved_count,
            "feedback_format": feedback_format,
        }

    header = (
        f"You are retrying benchmark task `{task.task_id}` after validator feedback.\n\n"
        f"Attempt completed: {attempt_number}\n"
        f"Validator score: {grade.score:.4f}/{grade.max_score:.4f}\n"
        "Task passes only when the score reaches the maximum.\n\n"
    )
    if feedback_policy == "vague":
        body = (
            "The previous attempt did not pass validation.\n\n"
            "Original grading criteria:\n"
            f"{criteria}\n\n"
            "Retry policy:\n"
            f"{_retry_policy_instructions(feedback_policy)}"
        )
    elif feedback_policy in {"actionable-path", "actionable-path-file"}:
        body = (
            "Unresolved validator issues:\n"
            f"{unresolved_breakdown}\n\n"
            "Validator notes:\n"
            f"{notes}\n\n"
            "Suggested repair plan:\n"
            f"{chr(10).join(_actionable_repair_steps(task, grade))}\n\n"
            "Original grading criteria:\n"
            f"{criteria}\n\n"
            "Retry policy:\n"
            f"{_retry_policy_instructions(feedback_policy)}"
        )
    else:
        body = (
            "Validator breakdown:\n"
            f"{full_breakdown}\n\n"
            "Validator notes:\n"
            f"{notes}\n\n"
            "Original grading criteria:\n"
            f"{criteria}\n\n"
            "Retry policy:\n"
            f"{_retry_policy_instructions(feedback_policy)}"
        )
    text = header + body
    return {
        "text": text,
        "text_length_chars": len(text),
        "stable_prefix_length_chars": 0,
        "dynamic_suffix_length_chars": len(text),
        "unresolved_criteria_count": unresolved_count,
        "feedback_format": feedback_format,
    }


def _compose_retry_prompt(
    task: Task,
    feedback_prompt: str,
    *,
    actionable_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    del task
    if actionable_history:
        history_blocks = "\n\n".join(
            _format_actionable_history_entry(entry) for entry in actionable_history
        )
        return (
            f"{feedback_prompt}\n\n"
            "Interactive human guidance history:\n"
            f"{history_blocks}\n\n"
            "Use the validator diagnosis above as the primary source of failure information. "
            "Use the recorded quality diagnostics and the human next-step instruction to decide the next targeted fix. "
            "Preserve working parts unless the diagnosis or human instruction requires a broader change."
        )
    return feedback_prompt


def _unresolved_criteria_count(grade: GradeResult) -> int:
    return sum(1 for value in grade.breakdown.values() if value < 1.0)


def _score_delta(current_score: float, previous_score: Optional[float]) -> Optional[float]:
    if previous_score is None:
        return None
    return round(float(current_score) - float(previous_score), 6)


def _detect_infrastructure_failure(execution_result: Dict[str, Any]) -> Optional[Dict[str, str]]:
    stderr = str(execution_result.get("stderr") or "")
    stdout = str(execution_result.get("stdout") or "")
    combined = f"{stderr}\n{stdout}".lower()
    status = str(execution_result.get("status") or "")

    patterns = {
        "rate-limit": (
            "rate limit reached",
            "rate_limit",
            "too many requests",
            "429",
            "usage limit exceeded",
            "quota exceeded",
            "insufficient_quota",
            "exceeded your current quota",
        ),
        "gateway-closed": (
            "gateway closed",
            "abnormal closure",
            "no close reason",
            "websocket closed",
        ),
        "provider-unavailable": (
            "service unavailable",
            "bad gateway",
            "gateway timeout",
            "connection reset",
            "connection refused",
            "temporary failure",
        ),
    }

    for reason, markers in patterns.items():
        if any(marker in combined for marker in markers):
            return {
                "category": "infrastructure-failure",
                "reason": reason,
                "message": stderr.strip() or stdout.strip() or reason,
            }

    if status == "error" and not execution_result.get("transcript"):
        return {
            "category": "infrastructure-failure",
            "reason": "empty-error-transcript",
            "message": stderr.strip() or stdout.strip() or "Execution failed before agent output was recorded.",
        }

    return None


def _extract_quota_limit_failure(outcome: Dict[str, Any]) -> Optional[Dict[str, str]]:
    result = outcome.get("result", {})
    infrastructure_failure = result.get("infrastructure_failure")
    if (
        isinstance(infrastructure_failure, dict)
        and infrastructure_failure.get("reason") == "rate-limit"
    ):
        return infrastructure_failure

    attempts = outcome.get("attempts", [])
    for attempt in attempts:
        infrastructure_failure = attempt.get("infrastructure_failure")
        if (
            isinstance(infrastructure_failure, dict)
            and infrastructure_failure.get("reason") == "rate-limit"
        ):
            return infrastructure_failure

        execution = attempt.get("execution", {})
        detected = _detect_infrastructure_failure(execution)
        if detected is not None and detected.get("reason") == "rate-limit":
            return detected

    return None


def _should_stop_retry(
    *,
    stop_rule: str,
    stop_threshold: float,
    current_score: float,
    previous_score: Optional[float],
    current_unresolved_count: int,
    previous_unresolved_count: Optional[int],
    token_delta: float,
    previous_attempt_summary: Optional[Dict[str, Any]] = None,
    current_attempt_summary: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    if stop_rule == "max-attempts-only":
        return None

    if stop_rule == "verifier-narrowing":
        if previous_attempt_summary is None or current_attempt_summary is None:
            return None
        decision = decide_inter_attempt_stop(previous_attempt_summary, current_attempt_summary)
        if decision.should_stop:
            return "verifier-not-narrowing"
        return None

    score_delta = _score_delta(current_score, previous_score)
    if stop_rule in ("no-improvement", "score-stall"):
        if score_delta is not None and score_delta <= stop_threshold:
            return "score-stall"
        return None

    if stop_rule == "unresolved-stall":
        if (
            previous_unresolved_count is not None
            and current_unresolved_count >= previous_unresolved_count
        ):
            return "unresolved-stall"
        return None

    if stop_rule == "low-return":
        if score_delta is None:
            return None
        if token_delta <= 0:
            return "low-return"
        improvement_per_1k_tokens = (score_delta / token_delta) * 1000.0
        if improvement_per_1k_tokens <= stop_threshold:
            return "low-return"
    return None


def _execution_was_intra_attempt_early_stopped(execution: Dict[str, Any]) -> bool:
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


def _usage_delta(current: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not previous:
        return dict(current)
    delta: Dict[str, Any] = {}
    for key, value in current.items():
        prev_value = previous.get(key, 0)
        if isinstance(value, float) or isinstance(prev_value, float):
            delta[key] = round(float(value) - float(prev_value), 6)
        else:
            delta[key] = int(value) - int(prev_value)
    return delta


def _usage_round_delta(
    current_rounds: List[Dict[str, Any]],
    previous_rounds: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    previous_count = len(previous_rounds or [])
    new_rounds = current_rounds[previous_count:]
    normalized = []
    for idx, round_usage in enumerate(new_rounds, start=1):
        normalized.append({
            **round_usage,
            "round": idx,
        })
    return normalized


def _execution_time_delta(current: float, previous: Optional[float]) -> float:
    if previous is None:
        return round(float(current), 6)
    return round(float(current) - float(previous), 6)


def _aggregate_attempt_usage(attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "request_count": 0,
    }
    for attempt in attempts:
        usage = attempt.get("execution", {}).get("usage", {})
        totals["input_tokens"] += int(usage.get("input_tokens", 0))
        totals["output_tokens"] += int(usage.get("output_tokens", 0))
        totals["cache_read_tokens"] += int(usage.get("cache_read_tokens", 0))
        totals["cache_write_tokens"] += int(usage.get("cache_write_tokens", 0))
        totals["total_tokens"] += int(usage.get("total_tokens", 0))
        totals["cost_usd"] += float(usage.get("cost_usd", 0.0) or 0.0)
        totals["request_count"] += int(usage.get("request_count", 0))
    totals["cost_usd"] = round(totals["cost_usd"], 6)
    return totals


def _aggregate_attempt_execution_time(attempts: List[Dict[str, Any]]) -> float:
    total = 0.0
    for attempt in attempts:
        execution = attempt.get("execution", {})
        total += float(execution.get("execution_time", 0.0) or 0.0)
    return round(total, 6)


def _aggregate_attempt_round_usage(attempts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rounds: List[Dict[str, Any]] = []
    for attempt in attempts:
        for round_usage in attempt.get("execution", {}).get("usage_per_round", []):
            rounds.append({**round_usage})
    for idx, round_usage in enumerate(rounds, start=1):
        round_usage["round"] = idx
    return rounds


def _execute_task_with_feedback(
    *,
    task: Task,
    agent_id: str,
    model_id: str,
    run_id: str,
    timeout_multiplier: float,
    skill_dir: Path,
    max_task_attempts: int,
    feedback_policy: str,
    feedback_format: str,
    feedback_answer_safety: str,
    stop_rule: str,
    stop_threshold: float,
    judge_kw: Dict[str, Any],
    verbose: bool = False,
) -> Dict[str, Any]:
    attempt_summaries: List[Dict[str, Any]] = []
    actionable_history: List[Dict[str, Any]] = []
    execution_error = None
    stop_reason = "max-attempts-reached"
    infrastructure_failure: Optional[Dict[str, str]] = None
    previous_cumulative_usage: Optional[Dict[str, Any]] = None
    previous_cumulative_usage_per_round: Optional[List[Dict[str, Any]]] = None
    previous_cumulative_execution_time: Optional[float] = None
    previous_transcript_length: Optional[int] = None

    try:
        result = execute_openclaw_task(
            task=task,
            agent_id=agent_id,
            model_id=model_id,
            run_id=run_id,
            timeout_multiplier=timeout_multiplier,
            skill_dir=skill_dir,
            initial_workspace_snapshot=None,
            verbose=verbose,
        )
    except Exception as exc:
        execution_error = str(exc)
        logger.warning("Task execution failed for %s, continuing: %s", task.task_id, exc)
        result = {
            "agent_id": agent_id,
            "task_id": task.task_id,
            "status": "error",
            "transcript": [],
            "usage": {},
            "usage_per_round": [],
            "workspace": "",
            "exit_code": -1,
            "timed_out": False,
            "execution_time": 0.0,
            "stdout": "",
            "stderr": execution_error,
            "session_id": None,
            "initial_workspace_snapshot": None,
        }

    try:
        grade = grade_task(
            task=task,
            execution_result=result,
            skill_dir=skill_dir,
            verbose=verbose,
            **judge_kw,
        )
    except Exception as exc:
        note = (
            f"Execution failed: {execution_error}; Grading failed: {exc}"
            if execution_error
            else f"Grading failed: {exc}"
        )
        logger.warning("Task grading failed for %s, continuing: %s", task.task_id, exc)
        grade = GradeResult(
            task_id=task.task_id,
            score=0.0,
            max_score=1.0,
            grading_type=task.grading_type,
            breakdown={},
            notes=note,
        )

    attempt_summaries.append(
        {
            "attempt": 1,
            "execution": {
                **result,
                "cumulative_execution_time": round(float(result.get("execution_time", 0.0) or 0.0), 6),
                "cumulative_usage": dict(result.get("usage", {})),
                "cumulative_usage_per_round": list(result.get("usage_per_round", [])),
            },
            "grading": grade.to_dict(),
            "feedback_prompt": None,
            "feedback_prompt_stats": None,
            "feedback_policy": feedback_policy,
            "feedback_format": feedback_format,
            "interactive_actionable_feedback": None,
            "transcript_length": len(result.get("transcript", [])),
            "transcript_length_delta": len(result.get("transcript", [])),
            "score_delta": None,
            "unresolved_criteria_count": _unresolved_criteria_count(grade),
            "stop_rule": stop_rule,
            "stop_rule_threshold": stop_threshold,
            "stop_rule_triggered": False,
            "stop_rule_trigger_reason": None,
            "infrastructure_failure": _detect_infrastructure_failure(result),
        }
    )
    infrastructure_failure = attempt_summaries[-1]["infrastructure_failure"]
    previous_cumulative_usage = dict(result.get("usage", {}))
    previous_cumulative_usage_per_round = list(result.get("usage_per_round", []))
    previous_cumulative_execution_time = round(float(result.get("execution_time", 0.0) or 0.0), 6)
    previous_transcript_length = len(result.get("transcript", []))
    score_pct_1 = grade.score / grade.max_score * 100 if grade.max_score > 0 else 0
    logger.info(
        "   📊 Attempt 1/%s score: %.2f/%.2f (%.0f%%)",
        max(1, max_task_attempts),
        grade.score,
        grade.max_score,
        score_pct_1,
    )

    max_attempts = max(1, max_task_attempts)
    previous_score = grade.score
    for attempt_number in range(2, max_attempts + 1):
        if _grade_passed(grade):
            stop_reason = "passed"
            break

        if _execution_was_intra_attempt_early_stopped(attempt_summaries[-1].get("execution", {})):
            logger.info(
                "Stopping retries for %s because the previous attempt triggered intra-attempt early stop",
                task.task_id,
            )
            stop_reason = "intra-attempt-early-stop"
            break

        if infrastructure_failure is not None:
            logger.info(
                "Stopping retries for %s because of infrastructure failure: %s",
                task.task_id,
                infrastructure_failure.get("reason", "unknown"),
            )
            stop_reason = infrastructure_failure.get("category", "infrastructure-failure")
            break

        if not result.get("workspace") or not result.get("session_id"):
            logger.info(
                "Stopping retries for %s because workspace/session context is unavailable",
                task.task_id,
            )
            stop_reason = "missing-workspace-or-session"
            break

        feedback_payload = _build_iteration_feedback(
            task,
            grade,
            attempt_number - 1,
            feedback_policy=feedback_policy,
            feedback_format=feedback_format,
            feedback_answer_safety=feedback_answer_safety,
        )
        feedback_prompt = feedback_payload["text"]
        interactive_feedback = None
        if _interactive_actionable_enabled(feedback_policy):
            interactive_feedback = _collect_interactive_actionable_feedback(
                task=task,
                attempt_number=attempt_number - 1,
                grade=grade,
                previous_attempt_summary=(
                    attempt_summaries[-2] if len(attempt_summaries) >= 2 else None
                ),
                transcript_length_delta=attempt_summaries[-1].get("transcript_length_delta"),
                answer_safety=feedback_answer_safety,
            )
            actionable_history.append(interactive_feedback)

        logger.info(
            "🔁 Retrying %s with validator feedback (%s/%s)",
            task.task_id,
            attempt_number,
            max_attempts,
        )

        retry_workspace = Path(result["workspace"])
        retry_session_id = result["session_id"]
        retry_prompt = _compose_retry_prompt(
            task,
            feedback_prompt,
            actionable_history=actionable_history if actionable_history else None,
        )
        feedback_payload = {
            **feedback_payload,
            "interactive_actionable": interactive_feedback is not None,
            "interactive_history_count": len(actionable_history),
            "text_length_chars_with_history": len(retry_prompt),
        }

        retry_result = _run_openclaw_message(
            agent_id=agent_id,
            prompt=retry_prompt,
            workspace=retry_workspace,
            session_id=retry_session_id,
            timeout_seconds=task.timeout_seconds * timeout_multiplier,
        )
        execution_payload = {
            **retry_result,
            "cumulative_execution_time": round(
                float(retry_result.get("execution_time", 0.0) or 0.0), 6
            ),
            "execution_time": _execution_time_delta(
                float(retry_result.get("execution_time", 0.0) or 0.0),
                previous_cumulative_execution_time,
            ),
            "cumulative_usage": dict(retry_result.get("usage", {})),
            "cumulative_usage_per_round": list(retry_result.get("usage_per_round", [])),
            "usage": _usage_delta(retry_result.get("usage", {}), previous_cumulative_usage),
            "usage_per_round": _usage_round_delta(
                retry_result.get("usage_per_round", []),
                previous_cumulative_usage_per_round,
            ),
        }
        result = {
            **execution_payload,
            "agent_id": agent_id,
            "task_id": task.task_id,
            "initial_workspace_snapshot": result.get("initial_workspace_snapshot"),
        }
        if "cumulative_execution_time" not in result:
            result["cumulative_execution_time"] = round(
                float(result.get("execution_time", 0.0) or 0.0)
                + float(previous_cumulative_execution_time or 0.0),
                6,
            )

        try:
            grade = grade_task(
                task=task,
                execution_result=result,
                skill_dir=skill_dir,
                verbose=verbose,
                **judge_kw,
            )
        except Exception as exc:
            logger.warning(
                "Task grading failed during retry for %s, continuing: %s",
                task.task_id,
                exc,
            )
            grade = GradeResult(
                task_id=task.task_id,
                score=0.0,
                max_score=1.0,
                grading_type=task.grading_type,
                breakdown={},
                notes=f"Retry grading failed: {exc}",
            )
        transcript_length = len(result.get("transcript", []))
        transcript_length_delta = transcript_length - int(previous_transcript_length or 0)
        unresolved_count = _unresolved_criteria_count(grade)
        score_delta = _score_delta(grade.score, previous_score)
        token_delta = float(result.get("usage", {}).get("total_tokens", 0) or 0.0)
        current_infrastructure_failure = _detect_infrastructure_failure(result)
        stop_trigger_reason = _should_stop_retry(
            stop_rule=stop_rule,
            stop_threshold=stop_threshold,
            current_score=grade.score,
            previous_score=previous_score,
            current_unresolved_count=unresolved_count,
            previous_unresolved_count=attempt_summaries[-1].get("unresolved_criteria_count"),
            token_delta=token_delta,
            previous_attempt_summary=attempt_summaries[-1],
            current_attempt_summary={
                "attempt": attempt_number,
                "grading": grade.to_dict(),
                "unresolved_criteria_count": unresolved_count,
                "verifier": {
                    "reward": grade.score,
                    "notes": grade.notes,
                    "feedback": list(grade.breakdown.keys()),
                },
            },
        )
        attempt_summaries.append(
            {
                "attempt": attempt_number,
                "execution": result,
                "grading": grade.to_dict(),
                "feedback_prompt": retry_prompt,
                "feedback_prompt_stats": feedback_payload,
                "feedback_policy": feedback_policy,
                "feedback_format": feedback_format,
                "interactive_actionable_feedback": interactive_feedback,
                "transcript_length": transcript_length,
                "transcript_length_delta": transcript_length_delta,
                "score_delta": score_delta,
                "unresolved_criteria_count": unresolved_count,
                "stop_rule": stop_rule,
                "stop_rule_threshold": stop_threshold,
                "stop_rule_triggered": stop_trigger_reason is not None,
                "stop_rule_trigger_reason": stop_trigger_reason,
                "infrastructure_failure": current_infrastructure_failure,
            }
        )
        infrastructure_failure = current_infrastructure_failure
        previous_cumulative_usage = dict(
            execution_payload.get("cumulative_usage", execution_payload.get("usage", {}))
        )
        previous_cumulative_usage_per_round = list(
            execution_payload.get("cumulative_usage_per_round", execution_payload.get("usage_per_round", []))
        )
        previous_cumulative_execution_time = round(
            float(
                execution_payload.get(
                    "cumulative_execution_time",
                    execution_payload.get("execution_time", 0.0),
                )
                or 0.0
            ),
            6,
        )
        previous_transcript_length = transcript_length
        score_pct = grade.score / grade.max_score * 100 if grade.max_score > 0 else 0
        logger.info(
            "   📊 Attempt %s/%s score: %.2f/%.2f (%.0f%%)",
            attempt_number,
            max_attempts,
            grade.score,
            grade.max_score,
            score_pct,
        )
        if stop_trigger_reason is not None:
            logger.info(
                "   ⏹️  Stopping retries for %s because %s",
                task.task_id,
                stop_trigger_reason,
            )
            stop_reason = stop_trigger_reason
            break
        previous_score = grade.score

    if _grade_passed(grade):
        stop_reason = "passed"
    elif infrastructure_failure is not None:
        stop_reason = infrastructure_failure.get("category", "infrastructure-failure")
        result["status"] = infrastructure_failure.get("category", "infrastructure-failure")
        result["infrastructure_failure"] = infrastructure_failure

    return {
        "result": result,
        "grade": grade,
        "attempts": attempt_summaries,
        "stop_reason": stop_reason,
    }


def _json_sanitize(obj: Any) -> Any:
    """Recursively convert structures so they are JSON-serializable (e.g. bytes -> placeholder)."""
    if isinstance(obj, bytes):
        return f"<bytes length={len(obj)}>"
    if isinstance(obj, dict):
        return {k: _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_sanitize(v) for v in obj]
    return obj


def _first_success_attempt(attempts: List[Dict[str, Any]]) -> Optional[int]:
    for attempt in attempts:
        grading = attempt.get("grading", {})
        score = float(grading.get("score", 0.0))
        max_score = float(grading.get("max_score", 0.0))
        if max_score > 0 and score >= max_score:
            return int(attempt.get("attempt", 0))
    return None


def _aggregate_judge_usage(grading: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Aggregate judge_usage from all runs in grading. Returns None if no run used judge."""
    runs = grading.get("runs", [])
    usages = [r.get("judge_usage") for r in runs if isinstance(r.get("judge_usage"), dict)]
    if not usages:
        return None
    agg = {
        "model": usages[0].get("model", ""),
        "input_tokens": sum(int(u.get("input_tokens", 0)) for u in usages),
        "output_tokens": sum(int(u.get("output_tokens", 0)) for u in usages),
        "total_tokens": sum(int(u.get("total_tokens", 0)) for u in usages),
        "cost_usd": round(sum(float(u.get("cost_usd", 0) or 0) for u in usages), 6),
        "execution_time_seconds": round(
            sum(float(u.get("execution_time_seconds", 0) or 0) for u in usages), 3
        ),
        "request_count": sum(int(u.get("request_count", 0)) for u in usages),
    }
    if len(usages) > 1:
        agg["runs"] = len(usages)
    return agg


def _compute_efficiency_summary(
    task_entries: List[Dict[str, Any]],
    grades_by_task_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute aggregate token efficiency metrics across all tasks.

    Returns a dict with total token usage, cost, and efficiency ratios
    (score per token, score per dollar) so that different models can be
    compared not just on quality but also on resource consumption.
    """
    total_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0
    total_cost_usd = 0.0
    total_requests = 0
    total_execution_time = 0.0
    tasks_with_usage = 0
    successful_tasks = 0

    per_task_efficiency: List[Dict[str, Any]] = []
    for entry in task_entries:
        usage = entry.get("usage", {})
        task_id = entry["task_id"]
        grading = grades_by_task_id.get(task_id, {})
        score = float(grading.get("mean", 0.0))
        passed = bool(entry.get("completion", {}).get("passed", False))

        inp = int(usage.get("input_tokens", 0))
        out = int(usage.get("output_tokens", 0))
        tot = int(usage.get("total_tokens", 0))
        cost = float(usage.get("cost_usd", 0.0) or 0.0)
        reqs = int(usage.get("request_count", 0))
        exec_time = float(entry.get("execution_time", 0.0) or 0.0)

        total_input_tokens += inp
        total_output_tokens += out
        total_tokens += tot
        total_cost_usd += cost
        total_requests += reqs
        total_execution_time += exec_time
        if passed:
            successful_tasks += 1

        if tot > 0:
            tasks_with_usage += 1

        per_task_efficiency.append({
            "task_id": task_id,
            "score": round(score, 4),
            "passed": passed,
            "total_tokens": tot,
            "cost_usd": round(cost, 6),
            "tokens_per_score_point": round(tot / score, 1) if score > 0 else None,
            "tokens_per_success": tot if passed else None,
        })

    # Aggregate scores
    all_scores = [
        float(g.get("mean", 0.0)) for g in grades_by_task_id.values()
    ]
    total_score = sum(all_scores)
    num_tasks = len(all_scores)

    summary: Dict[str, Any] = {
        "total_tokens": total_tokens,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost_usd": round(total_cost_usd, 6),
        "total_requests": total_requests,
        "total_execution_time_seconds": round(total_execution_time, 2),
        "tasks_with_usage_data": tasks_with_usage,
        "tokens_per_task": round(total_tokens / num_tasks, 1) if num_tasks > 0 else 0,
        "cost_per_task_usd": round(total_cost_usd / num_tasks, 6) if num_tasks > 0 else 0,
        "score_per_1k_tokens": (
            round(total_score / (total_tokens / 1000), 6)
            if total_tokens > 0
            else None
        ),
        "score_per_dollar": (
            round(total_score / total_cost_usd, 4)
            if total_cost_usd > 0
            else None
        ),
        "success_rate": round(successful_tasks / num_tasks, 6) if num_tasks > 0 else 0.0,
        "success_per_1k_tokens": (
            round(successful_tasks / (total_tokens / 1000), 6)
            if total_tokens > 0
            else None
        ),
        "success_per_dollar": (
            round(successful_tasks / total_cost_usd, 6)
            if total_cost_usd > 0
            else None
        ),
        "per_task": per_task_efficiency,
    }
    return summary


def _build_task_entries(
    run_outcomes: List[Dict[str, Any]],
    grades_by_task_id: Dict[str, Dict[str, Any]],
    tasks_by_id: Dict[str, Task],
    args: argparse.Namespace,
) -> List[Dict[str, Any]]:
    task_entries = []
    for outcome in run_outcomes:
        result = outcome["result"]
        task_id = result["task_id"]
        grading_summary = grades_by_task_id[task_id]
        run_grading = outcome["grade"].to_dict()
        total_usage = _aggregate_attempt_usage(outcome["attempts"])
        total_usage_per_round = _aggregate_attempt_round_usage(outcome["attempts"])
        total_execution_time = _aggregate_attempt_execution_time(outcome["attempts"])
        entry = {
            "task_id": task_id,
            "status": result["status"],
            "timed_out": result["timed_out"],
            "infrastructure_failure": result.get("infrastructure_failure"),
            "execution_time": total_execution_time,
            "transcript_length": len(result["transcript"]),
            "llm_rounds": len(total_usage_per_round),
            "usage": total_usage,
            "usage_per_round": total_usage_per_round,
            "workspace": result["workspace"],
            "grading": run_grading,
            "grading_summary": grading_summary,
            "completion": _completion_summary({"runs": [run_grading], "mean": run_grading["score"]}),
            "frontmatter": tasks_by_id[task_id].frontmatter,
            "attempt_count": len(outcome["attempts"]),
            "first_success_attempt": _first_success_attempt(outcome["attempts"]),
            "success_within_budget": _first_success_attempt(outcome["attempts"]) is not None,
            "unresolved_criteria_count_by_attempt": [
                attempt.get("unresolved_criteria_count") for attempt in outcome["attempts"]
            ],
            "transcript_length_by_attempt": [
                attempt.get("transcript_length") for attempt in outcome["attempts"]
            ],
            "prompt_tokens_by_attempt": [
                int(attempt.get("execution", {}).get("usage", {}).get("input_tokens", 0) or 0)
                for attempt in outcome["attempts"]
            ],
            "completion_tokens_by_attempt": [
                int(attempt.get("execution", {}).get("usage", {}).get("output_tokens", 0) or 0)
                for attempt in outcome["attempts"]
            ],
            "feedback_length_chars_by_attempt": [
                (
                    attempt.get("feedback_prompt_stats", {}) or {}
                ).get("text_length_chars")
                for attempt in outcome["attempts"]
            ],
            "stop_reason": outcome["stop_reason"],
            "attempts": outcome["attempts"],
            "retry_policies": {
                "feedback_policy": args.feedback_policy,
                "feedback_format": args.feedback_format,
                "stop_rule": args.stop_rule,
                "stop_threshold": args.stop_threshold,
                "actionable_mode": (
                    (
                        "interactive"
                        if args.feedback_policy == "actionable-path"
                        else "file"
                        if args.feedback_policy == "actionable-path-file"
                        else "static"
                    )
                ),
            },
        }
        judge_usage = _aggregate_judge_usage(grading_summary)
        if judge_usage is not None:
            entry["judge_usage"] = judge_usage
        task_entries.append(entry)
    return task_entries


def _build_judge_summary(task_entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    seen_judge_task_ids = set()
    judge_summary = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "execution_time_seconds": 0.0,
        "request_count": 0,
        "tasks_using_judge": 0,
    }
    for entry in task_entries:
        judge_usage = entry.get("judge_usage")
        if not isinstance(judge_usage, dict):
            continue
        task_id = entry["task_id"]
        if task_id in seen_judge_task_ids:
            continue
        seen_judge_task_ids.add(task_id)
        judge_summary["tasks_using_judge"] += 1
        judge_summary["input_tokens"] += int(judge_usage.get("input_tokens", 0))
        judge_summary["output_tokens"] += int(judge_usage.get("output_tokens", 0))
        judge_summary["total_tokens"] += int(judge_usage.get("total_tokens", 0))
        judge_summary["cost_usd"] += float(judge_usage.get("cost_usd", 0) or 0)
        judge_summary["execution_time_seconds"] += float(
            judge_usage.get("execution_time_seconds", 0) or 0
        )
        judge_summary["request_count"] += int(judge_usage.get("request_count", 0))
    if not seen_judge_task_ids:
        return None
    judge_summary["cost_usd"] = round(judge_summary["cost_usd"], 6)
    judge_summary["execution_time_seconds"] = round(judge_summary["execution_time_seconds"], 3)
    return judge_summary


def _write_results_snapshot(output_path: Path, aggregate: Dict[str, Any]) -> None:
    temp_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temp_path.write_text(json.dumps(_json_sanitize(aggregate), indent=2), encoding="utf-8")
    temp_path.replace(output_path)


def _build_aggregate_payload(
    args: argparse.Namespace,
    skill_root: Path,
    run_id: str,
    runs_per_task: int,
    max_task_attempts: int,
    run_outcomes: List[Dict[str, Any]],
    grades_by_task_id: Dict[str, Dict[str, Any]],
    tasks_by_id: Dict[str, Task],
) -> Dict[str, Any]:
    task_entries = _build_task_entries(run_outcomes, grades_by_task_id, tasks_by_id, args)
    efficiency = _compute_efficiency_summary(task_entries, grades_by_task_id)
    aggregate = {
        "model": args.model,
        "benchmark_version": _get_git_version(skill_root),
        "run_id": run_id,
        "timestamp": time.time(),
        "suite": args.suite,
        "runs_per_task": runs_per_task,
        "max_task_attempts": max_task_attempts,
        "retry_policies": {
            "feedback_policy": args.feedback_policy,
            "feedback_format": args.feedback_format,
            "stop_rule": args.stop_rule,
            "stop_threshold": args.stop_threshold,
            "actionable_mode": (
                (
                    "interactive"
                    if args.feedback_policy == "actionable-path"
                    else "file"
                    if args.feedback_policy == "actionable-path-file"
                    else "static"
                )
            ),
        },
        "tasks": task_entries,
        "efficiency": efficiency,
    }
    judge_summary = _build_judge_summary(task_entries)
    if judge_summary is not None:
        aggregate["judge_summary"] = judge_summary
    return aggregate


def _log_efficiency_summary(
    efficiency: Dict[str, Any],
    grades_by_task_id: Dict[str, Dict[str, Any]],
) -> None:
    """Log a human-readable token efficiency summary."""
    all_scores = [
        float(g.get("mean", 0.0)) for g in grades_by_task_id.values()
    ]
    mean_score = statistics.mean(all_scores) if all_scores else 0.0

    logger.info("\n%s", "=" * 80)
    logger.info("📊 TOKEN EFFICIENCY SUMMARY")
    logger.info("%s", "=" * 80)
    logger.info(
        "   Total tokens used: %s (input: %s, output: %s)",
        f"{efficiency['total_tokens']:,}",
        f"{efficiency['total_input_tokens']:,}",
        f"{efficiency['total_output_tokens']:,}",
    )
    logger.info("   Total API requests: %s", f"{efficiency['total_requests']:,}")
    if efficiency["total_cost_usd"] > 0:
        logger.info("   Total cost: $%.4f", efficiency["total_cost_usd"])
    logger.info(
        "   Avg tokens/task: %s",
        f"{efficiency['tokens_per_task']:,.0f}",
    )
    logger.info("   Mean score: %.4f", mean_score)
    logger.info("   Success rate: %.4f", efficiency.get("success_rate", 0.0))
    if efficiency.get("score_per_1k_tokens") is not None:
        logger.info(
            "   Score per 1K tokens: %.4f (higher = more efficient)",
            efficiency["score_per_1k_tokens"],
        )
    if efficiency.get("success_per_1k_tokens") is not None:
        logger.info(
            "   Success per 1K tokens: %.6f (higher = more efficient)",
            efficiency["success_per_1k_tokens"],
        )
    if efficiency.get("score_per_dollar") is not None:
        logger.info(
            "   Score per dollar: %.4f (higher = more cost-efficient)",
            efficiency["score_per_dollar"],
        )
    if efficiency.get("success_per_dollar") is not None:
        logger.info(
            "   Success per dollar: %.6f (higher = more cost-efficient)",
            efficiency["success_per_dollar"],
        )
    logger.info("%s", "=" * 80)


def main():
    """Main entry point for the benchmark script."""
    # Determine tasks directory
    script_dir = Path(__file__).parent
    skill_root = script_dir.parent  # Parent of scripts/ is the skill root
    tasks_dir = skill_root / "tasks"

    logger.info("🦞🦀🦐 PinchBench - OpenClaw Benchmarking")
    ascii_crab = _load_ascii_art(skill_root, "crab.txt")
    if ascii_crab:
        print("\n" + _colorize_gradient(ascii_crab) + "\n")
    else:
        print("\n" + "🦀 " * 30)
        print("🦀 " * 30 + "\n")
    logger.info("🦞🦀🦐 Starting PinchBench 🦐🦀🦞")
    time.sleep(5)

    if not tasks_dir.exists():
        logger.error(f"❌ Tasks directory not found: {tasks_dir}")
        sys.exit(1)

    args = _parse_args()
    if not args.model and not args.register and not args.upload:
        logger.error("Missing required argument: --model (unless using --register or --upload)")
        sys.exit(2)
    if (
        args.feedback_policy == "actionable-path"
        and args.max_task_attempts > 1
        and not sys.stdin.isatty()
    ):
        logger.error(
            "actionable-path with retries now requires an interactive terminal because it pauses for human guidance."
        )
        sys.exit(2)

    if args.register:
        try:
            from lib_upload import UploadError, register_token, save_token_config

            token, claim_url = register_token()
            config_path = save_token_config(token, claim_url)
            logger.info("Saved token to %s", config_path)
            if claim_url:
                logger.info("Claim URL: %s", claim_url)
            return
        except UploadError as exc:
            logger.error("Registration failed: %s", exc)
            sys.exit(1)

    if args.upload:
        results_path = Path(args.upload)
        if not results_path.exists():
            logger.error("Results file not found: %s", results_path)
            sys.exit(1)
        try:
            from lib_upload import UploadError, upload_results

            result = upload_results(results_path)
            if result.rank is not None:
                logger.info("Uploaded to leaderboard: rank #%s", result.rank)
            if result.leaderboard_url:
                logger.info("View at: %s", result.leaderboard_url)
            logger.info("Upload complete.")
            return
        except UploadError as exc:
            logger.error("Upload failed: %s", exc)
            sys.exit(1)

    logger.info("🔧 Initializing BenchmarkRunner...")
    runner = BenchmarkRunner(tasks_dir)

    logger.info("📂 Loading tasks from directory...")
    runner.load_tasks()

    model_slug = slugify_model(args.model)
    run_root = Path("/tmp/pinchbench")
    run_id = _next_run_id(run_root)
    skill_dir = skill_root
    agent_id = f"bench-{model_slug}"
    # Use a shared workspace for the agent - we'll copy fixtures per task
    agent_workspace = Path(f"/tmp/pinchbench/{run_id}/agent_workspace")

    ensure_agent_exists(agent_id, args.model, agent_workspace)
    cleanup_agent_sessions(agent_id)

    task_ids = _select_task_ids(runner.tasks, args.suite)
    run_outcomes = []
    grades_by_task_id = {}

    judge_api_key = args.judge_api_key or load_default_judge_api_key()
    judge_kw = {}
    if judge_api_key:
        judge_kw = {
            "judge_api_base": args.judge_api_base,
            "judge_api_model": args.judge_model,
            "judge_api_key": judge_api_key,
        }

    tasks_to_run = runner.tasks
    if task_ids is not None:
        tasks_to_run = [task for task in runner.tasks if task.task_id in task_ids]
    tasks_by_id = {task.task_id: task for task in tasks_to_run}

    runs_per_task = max(1, args.runs)
    max_task_attempts = max(1, args.max_task_attempts)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{run_id}_{model_slug}.json"
    for i, task in enumerate(tasks_to_run, 1):
        task_grades = []
        task_runs = []
        for run_index in range(runs_per_task):
            logger.info("\n%s", "=" * 80)
            logger.info(
                "📋 Task %s/%s (Run %s/%s)",
                i,
                len(tasks_to_run),
                run_index + 1,
                runs_per_task,
            )
            logger.info("%s", "=" * 80)
            outcome = _execute_task_with_feedback(
                task=task,
                agent_id=agent_id,
                model_id=args.model,
                run_id=f"{run_id}-{run_index + 1}",
                timeout_multiplier=args.timeout_multiplier,
                skill_dir=skill_dir,
                max_task_attempts=max_task_attempts,
                feedback_policy=args.feedback_policy,
                feedback_format=args.feedback_format,
                feedback_answer_safety=args.feedback_answer_safety,
                stop_rule=args.stop_rule,
                stop_threshold=args.stop_threshold,
                judge_kw=judge_kw,
                verbose=args.verbose,
            )
            result = outcome["result"]
            grade = outcome["grade"]
            task_grades.append(grade)
            task_runs.append(outcome)
            run_outcomes.append(outcome)

            # Log score immediately after grading
            score_pct = grade.score / grade.max_score * 100 if grade.max_score > 0 else 0
            status_emoji = (
                "✅" if grade.score >= grade.max_score else "⚠️" if grade.score > 0 else "❌"
            )
            logger.info(
                "%s Task %s: %.1f/%.1f (%.0f%%) - %s",
                status_emoji,
                task.task_id,
                grade.score,
                grade.max_score,
                score_pct,
                grade.grading_type,
            )
            if grade.notes:
                logger.info("   Notes: %s", grade.notes[:200])
            logger.info(
                "   Attempts used: %s/%s",
                len(outcome["attempts"]),
                max_task_attempts,
            )

            quota_limit_failure = _extract_quota_limit_failure(outcome)
            if quota_limit_failure is not None:
                grades_by_task_id[task.task_id] = {
                    "runs": [grade.to_dict() for grade in task_grades],
                    "mean": statistics.mean([task_grade.score for task_grade in task_grades]),
                    "std": (
                        statistics.stdev([task_grade.score for task_grade in task_grades])
                        if len(task_grades) > 1
                        else 0.0
                    ),
                    "min": min(task_grade.score for task_grade in task_grades),
                    "max": max(task_grade.score for task_grade in task_grades),
                    "attempts_per_run": [len(run["attempts"]) for run in task_runs],
                }
                aggregate = _build_aggregate_payload(
                    args=args,
                    skill_root=skill_root,
                    run_id=run_id,
                    runs_per_task=runs_per_task,
                    max_task_attempts=max_task_attempts,
                    run_outcomes=run_outcomes,
                    grades_by_task_id=grades_by_task_id,
                    tasks_by_id=tasks_by_id,
                )
                _write_results_snapshot(output_path, aggregate)
                logger.error(
                    "Quota limit hit on task %s (run %s/%s). Saved partial results to %s and exiting immediately.",
                    task.task_id,
                    run_index + 1,
                    runs_per_task,
                    output_path,
                )
                logger.error(
                    "Quota-limit detail: %s",
                    quota_limit_failure.get("message") or quota_limit_failure.get("reason"),
                )
                sys.exit(QUOTA_LIMIT_EXIT_CODE)

        task_scores = [grade.score for grade in task_grades]
        grades_by_task_id[task.task_id] = {
            "runs": [grade.to_dict() for grade in task_grades],
            "mean": statistics.mean(task_scores),
            "std": statistics.stdev(task_scores) if len(task_scores) > 1 else 0.0,
            "min": min(task_scores),
            "max": max(task_scores),
            "attempts_per_run": [len(run["attempts"]) for run in task_runs],
        }
        aggregate = _build_aggregate_payload(
            args=args,
            skill_root=skill_root,
            run_id=run_id,
            runs_per_task=runs_per_task,
            max_task_attempts=max_task_attempts,
            run_outcomes=run_outcomes,
            grades_by_task_id=grades_by_task_id,
            tasks_by_id=tasks_by_id,
        )
        _write_results_snapshot(output_path, aggregate)
        logger.info(
            "Saved interim results to %s after task %s (%s/%s)",
            output_path,
            task.task_id,
            i,
            len(tasks_to_run),
        )

    aggregate = _build_aggregate_payload(
        args=args,
        skill_root=skill_root,
        run_id=run_id,
        runs_per_task=runs_per_task,
        max_task_attempts=max_task_attempts,
        run_outcomes=run_outcomes,
        grades_by_task_id=grades_by_task_id,
        tasks_by_id=tasks_by_id,
    )
    _write_results_snapshot(output_path, aggregate)

    logger.info("Saved results to %s", output_path)
    efficiency = aggregate["efficiency"]
    _log_efficiency_summary(efficiency, grades_by_task_id)
    if args.no_upload:
        logger.info("Skipping upload (--no-upload)")
    else:
        try:
            from lib_upload import UploadError, upload_results

            result = upload_results(output_path, official_key=args.official_key)
            if result.rank is not None:
                logger.info("Uploaded to leaderboard: rank #%s", result.rank)
            if result.leaderboard_url:
                logger.info("View at: %s", result.leaderboard_url)
        except UploadError as exc:
            logger.warning("Upload failed: %s", exc)


if __name__ == "__main__":
    main()
