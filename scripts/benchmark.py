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

from lib_agent import (
    _run_openclaw_message,
    cleanup_agent_sessions,
    ensure_agent_exists,
    execute_openclaw_task,
    slugify_model,
)
from lib_grading import (
    GradeResult,
    KIMI_JUDGE_API_BASE,
    KIMI_JUDGE_API_KEY_DEFAULT,
    KIMI_JUDGE_MODEL,
    grade_task,
)
from lib_tasks import Task, TaskLoader


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("benchmark.log")],
)

logger = logging.getLogger("benchmark")


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
        choices=("vague", "error-localized", "actionable-path"),
        default="error-localized",
        help="Retry feedback content policy",
    )
    parser.add_argument(
        "--feedback-format",
        choices=("full-refresh", "stable-prefix"),
        default="full-refresh",
        help="Retry feedback formatting policy",
    )
    parser.add_argument(
        "--context-policy",
        choices=("append", "fresh-session", "rollback"),
        default="append",
        help="Retry context policy",
    )
    parser.add_argument(
        "--stop-rule",
        choices=("no-improvement", "max-attempts-only"),
        default="no-improvement",
        help="Rule for stopping validator-feedback retries",
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
        help="LLM judge API base URL (e.g. https://api.moonshot.cn/v1). Set with --judge-model and --judge-api-key to use Kimi judge.",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default=KIMI_JUDGE_MODEL,
        help="LLM judge model name (e.g. kimi-k2.5).",
    )
    parser.add_argument(
        "--judge-api-key",
        type=str,
        default=None,
        help="LLM judge API key. Defaults to env PINCHBENCH_KIMI_JUDGE_API_KEY or built-in Kimi key.",
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


def _retry_policy_instructions(feedback_policy: str) -> str:
    if feedback_policy == "vague":
        return (
            "- Continue working in the same workspace.\n"
            "- Do not restart from scratch unless necessary.\n"
            "- Make the minimal changes needed to pass validation.\n"
            "- When you are done, provide the updated final answer."
        )
    if feedback_policy == "actionable-path":
        return (
            "- Continue working in the same workspace.\n"
            "- Do not restart from scratch unless necessary.\n"
            "- Address only unresolved issues.\n"
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


def _actionable_repair_steps(grade: GradeResult) -> List[str]:
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


def _build_iteration_feedback(
    task: Task,
    grade: GradeResult,
    attempt_number: int,
    *,
    feedback_policy: str,
    feedback_format: str,
) -> str:
    notes = grade.notes.strip() if grade.notes else "No additional validator notes."
    criteria = "\n".join(f"- {item}" for item in task.grading_criteria) or "- None provided."
    full_breakdown = "\n".join(_format_breakdown_lines(grade))
    unresolved_breakdown = "\n".join(_format_breakdown_lines(grade, unresolved_only=True))

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
                f"{chr(10).join(_actionable_repair_steps(grade))}\n\n"
                "Validator notes:\n"
                f"{notes}"
            )
        return stable_prefix + dynamic_suffix

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
    elif feedback_policy == "actionable-path":
        body = (
            "Unresolved validator issues:\n"
            f"{unresolved_breakdown}\n\n"
            "Validator notes:\n"
            f"{notes}\n\n"
            "Suggested repair plan:\n"
            f"{chr(10).join(_actionable_repair_steps(grade))}\n\n"
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
    return header + body


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
    context_policy: str,
    stop_rule: str,
    judge_kw: Dict[str, Any],
    verbose: bool = False,
) -> Dict[str, Any]:
    attempt_summaries: List[Dict[str, Any]] = []
    execution_error = None

    try:
        result = execute_openclaw_task(
            task=task,
            agent_id=agent_id,
            model_id=model_id,
            run_id=run_id,
            timeout_multiplier=timeout_multiplier,
            skill_dir=skill_dir,
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
            "execution": result,
            "grading": grade.to_dict(),
            "feedback_prompt": None,
            "feedback_policy": feedback_policy,
            "feedback_format": feedback_format,
            "context_policy": context_policy,
        }
    )
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
            break

        if not result.get("workspace") or not result.get("session_id"):
            logger.info(
                "Stopping retries for %s because workspace/session context is unavailable",
                task.task_id,
            )
            break

        feedback_prompt = _build_iteration_feedback(
            task,
            grade,
            attempt_number - 1,
            feedback_policy=feedback_policy,
            feedback_format=feedback_format,
        )
        logger.info(
            "🔁 Retrying %s with validator feedback (%s/%s)",
            task.task_id,
            attempt_number,
            max_attempts,
        )

        retry_result = _run_openclaw_message(
            agent_id=agent_id,
            prompt=feedback_prompt,
            workspace=Path(result["workspace"]),
            session_id=result["session_id"],
            timeout_seconds=task.timeout_seconds * timeout_multiplier,
        )
        result = {
            **retry_result,
            "agent_id": agent_id,
            "task_id": task.task_id,
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
        attempt_summaries.append(
            {
                "attempt": attempt_number,
                "execution": result,
                "grading": grade.to_dict(),
                "feedback_prompt": feedback_prompt,
                "feedback_policy": feedback_policy,
                "feedback_format": feedback_format,
                "context_policy": context_policy,
            }
        )
        score_pct = grade.score / grade.max_score * 100 if grade.max_score > 0 else 0
        logger.info(
            "   📊 Attempt %s/%s score: %.2f/%.2f (%.0f%%)",
            attempt_number,
            max_attempts,
            grade.score,
            grade.max_score,
            score_pct,
        )
        if stop_rule == "no-improvement" and grade.score == previous_score:
            logger.info(
                "   ⏹️  Stopping retries for %s because score did not improve (%.2f)",
                task.task_id,
                grade.score,
            )
            break
        previous_score = grade.score

    return {
        "result": result,
        "grade": grade,
        "attempts": attempt_summaries,
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

    per_task_efficiency: List[Dict[str, Any]] = []
    for entry in task_entries:
        usage = entry.get("usage", {})
        task_id = entry["task_id"]
        grading = grades_by_task_id.get(task_id, {})
        score = float(grading.get("mean", 0.0))

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

        if tot > 0:
            tasks_with_usage += 1

        per_task_efficiency.append({
            "task_id": task_id,
            "score": round(score, 4),
            "total_tokens": tot,
            "cost_usd": round(cost, 6),
            "tokens_per_score_point": round(tot / score, 1) if score > 0 else None,
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
        "per_task": per_task_efficiency,
    }
    return summary


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
    if efficiency.get("score_per_1k_tokens") is not None:
        logger.info(
            "   Score per 1K tokens: %.4f (higher = more efficient)",
            efficiency["score_per_1k_tokens"],
        )
    if efficiency.get("score_per_dollar") is not None:
        logger.info(
            "   Score per dollar: %.4f (higher = more cost-efficient)",
            efficiency["score_per_dollar"],
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

    judge_api_key = args.judge_api_key or os.environ.get(
        "PINCHBENCH_KIMI_JUDGE_API_KEY", KIMI_JUDGE_API_KEY_DEFAULT
    )
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
                context_policy=args.context_policy,
                stop_rule=args.stop_rule,
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

        task_scores = [grade.score for grade in task_grades]
        grades_by_task_id[task.task_id] = {
            "runs": [grade.to_dict() for grade in task_grades],
            "mean": statistics.mean(task_scores),
            "std": statistics.stdev(task_scores) if len(task_scores) > 1 else 0.0,
            "min": min(task_scores),
            "max": max(task_scores),
            "attempts_per_run": [len(run["attempts"]) for run in task_runs],
        }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    task_entries = []
    for outcome in run_outcomes:
        result = outcome["result"]
        task_id = result["task_id"]
        grading = grades_by_task_id[task_id]
        entry = {
            "task_id": task_id,
            "status": result["status"],
            "timed_out": result["timed_out"],
            "execution_time": result["execution_time"],
            "transcript_length": len(result["transcript"]),
            "llm_rounds": len(result.get("usage_per_round", [])),
            "usage": result.get("usage", {}),
            "usage_per_round": result.get("usage_per_round", []),
            "workspace": result["workspace"],
            "grading": grading,
            "completion": _completion_summary(grading),
            "frontmatter": tasks_by_id[task_id].frontmatter,
            "attempt_count": len(outcome["attempts"]),
            "attempts": outcome["attempts"],
            "retry_policies": {
                "feedback_policy": args.feedback_policy,
                "feedback_format": args.feedback_format,
                "context_policy": args.context_policy,
                "stop_rule": args.stop_rule,
            },
        }
        judge_usage = _aggregate_judge_usage(grading)
        if judge_usage is not None:
            entry["judge_usage"] = judge_usage
        task_entries.append(entry)

    efficiency = _compute_efficiency_summary(task_entries, grades_by_task_id)

    judge_summary = None
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
    for e in task_entries:
        ju = e.get("judge_usage")
        if not isinstance(ju, dict):
            continue
        tid = e["task_id"]
        if tid in seen_judge_task_ids:
            continue
        seen_judge_task_ids.add(tid)
        judge_summary["tasks_using_judge"] += 1
        judge_summary["input_tokens"] += int(ju.get("input_tokens", 0))
        judge_summary["output_tokens"] += int(ju.get("output_tokens", 0))
        judge_summary["total_tokens"] += int(ju.get("total_tokens", 0))
        judge_summary["cost_usd"] += float(ju.get("cost_usd", 0) or 0)
        judge_summary["execution_time_seconds"] += float(ju.get("execution_time_seconds", 0) or 0)
        judge_summary["request_count"] += int(ju.get("request_count", 0))
    if seen_judge_task_ids:
        judge_summary["cost_usd"] = round(judge_summary["cost_usd"], 6)
        judge_summary["execution_time_seconds"] = round(judge_summary["execution_time_seconds"], 3)
    else:
        judge_summary = None

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
            "context_policy": args.context_policy,
            "stop_rule": args.stop_rule,
        },
        "tasks": task_entries,
        "efficiency": efficiency,
    }
    if judge_summary is not None:
        aggregate["judge_summary"] = judge_summary

    output_path = output_dir / f"{run_id}_{model_slug}.json"
    output_path.write_text(
        json.dumps(_json_sanitize(aggregate), indent=2), encoding="utf-8"
    )

    logger.info("Saved results to %s", output_path)
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
