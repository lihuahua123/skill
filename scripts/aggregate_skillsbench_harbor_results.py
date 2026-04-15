#!/usr/bin/env python3
"""
Aggregate Harbor SkillsBench job outputs into the retry analysis JSON schema.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate Harbor SkillsBench job outputs into a benchmark result JSON."
    )
    parser.add_argument("--jobs-root", required=True, type=Path)
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--agent", default="terminus-2")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--suite", default="all")
    parser.add_argument("--max-task-attempts", type=int, default=1)
    parser.add_argument("--benchmark-version", default="skillsbench")
    parser.add_argument("--feedback-policy", default="none")
    parser.add_argument("--feedback-format", default="none")
    parser.add_argument("--feedback-strategy", default="none")
    parser.add_argument("--feedback-answer-safety", default="no-answers")
    parser.add_argument("--stop-rule", default="max-attempts-only")
    parser.add_argument("--stop-threshold", default="0.0")
    parser.add_argument("--sandbox", default="docker")
    parser.add_argument("--mode", default="with-skills")
    parser.add_argument("--early-stop-intra-attempt", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _duration_seconds(start: Any, end: Any) -> float:
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    if start_dt is None or end_dt is None:
        return 0.0
    return max((end_dt - start_dt).total_seconds(), 0.0)


def _load_reward_from_file(trial_dir: Path) -> float | None:
    txt_path = trial_dir / "verifier" / "reward.txt"
    if txt_path.exists():
        try:
            return float(txt_path.read_text(encoding="utf-8").strip())
        except Exception:
            pass

    json_path = trial_dir / "verifier" / "reward.json"
    if json_path.exists():
        payload = _read_json(json_path)
        if isinstance(payload, dict):
            if "reward" in payload:
                return _to_float(payload.get("reward"), default=0.0)
            for value in payload.values():
                try:
                    return float(value)
                except Exception:
                    continue
    return None


def _extract_reward(trial_payload: dict[str, Any], trial_dir: Path) -> float:
    verifier_result = trial_payload.get("verifier_result")
    if isinstance(verifier_result, dict):
        rewards = verifier_result.get("rewards")
        if isinstance(rewards, dict):
            if "reward" in rewards:
                return _to_float(rewards.get("reward"), default=0.0)
            for key in ("score", "success", "pass"):
                if key in rewards:
                    return _to_float(rewards.get(key), default=0.0)
            for value in rewards.values():
                try:
                    return float(value)
                except Exception:
                    continue
        elif isinstance(rewards, (float, int)):
            return float(rewards)

    fallback = _load_reward_from_file(trial_dir)
    if fallback is not None:
        return fallback
    return 0.0


def _extract_transcript_length(trial_dir: Path) -> int:
    traj_path = trial_dir / "agent" / "trajectory.json"
    payload = _read_json(traj_path)
    if not isinstance(payload, dict):
        return 0
    steps = payload.get("steps")
    if isinstance(steps, list):
        return len(steps)
    return 0


def _extract_trial_entry(trial_dir: Path) -> dict[str, Any] | None:
    payload = _read_json(trial_dir / "result.json")
    if not isinstance(payload, dict):
        return None

    task_name = str(payload.get("task_name") or trial_dir.name.split("__")[0])
    trial_name = str(payload.get("trial_name") or trial_dir.name)

    agent_result = payload.get("agent_result")
    if not isinstance(agent_result, dict):
        agent_result = {}
    verifier_result = payload.get("verifier_result")
    if not isinstance(verifier_result, dict):
        verifier_result = {}
    exception_info = payload.get("exception_info")
    if not isinstance(exception_info, dict):
        exception_info = {}

    prompt_tokens = _to_int(agent_result.get("n_input_tokens"), default=0)
    completion_tokens = _to_int(agent_result.get("n_output_tokens"), default=0)
    cache_tokens = _to_int(agent_result.get("n_cache_tokens"), default=0)
    total_tokens = prompt_tokens + completion_tokens
    if total_tokens <= 0 and cache_tokens > 0:
        total_tokens = cache_tokens

    reward = _extract_reward(payload, trial_dir)
    reward = max(0.0, min(1.0, reward))
    passed = reward >= 1.0

    metadata = agent_result.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    llm_rounds = metadata.get("n_episodes")
    if llm_rounds is None:
        llm_rounds = metadata.get("n_rounds")
    llm_rounds = _to_int(llm_rounds, default=0)

    verifier_timing = payload.get("verifier")
    if not isinstance(verifier_timing, dict):
        verifier_timing = {}
    agent_exec_timing = payload.get("agent_execution")
    if not isinstance(agent_exec_timing, dict):
        agent_exec_timing = {}

    verifier_started = verifier_timing.get("started_at")
    verifier_finished = verifier_timing.get("finished_at")
    agent_exec_started = agent_exec_timing.get("started_at")
    agent_exec_finished = agent_exec_timing.get("finished_at")

    reward_path = ""
    if (trial_dir / "verifier" / "reward.txt").exists():
        reward_path = str(trial_dir / "verifier" / "reward.txt")
    elif (trial_dir / "verifier" / "reward.json").exists():
        reward_path = str(trial_dir / "verifier" / "reward.json")

    error_payload: dict[str, Any] = {}
    if exception_info:
        error_payload = {
            "exception_type": exception_info.get("exception_type"),
            "exception_message": exception_info.get("exception_message"),
            "exception_traceback": exception_info.get("exception_traceback"),
            "occurred_at": exception_info.get("occurred_at"),
        }

    timed_out = False
    exception_type = str(exception_info.get("exception_type") or "")
    intra_attempt_early_stop = exception_type == "IntraAttemptEarlyStop" or (trial_dir / "early_stop.json").exists()
    if exception_type in {"AgentTimeoutError", "VerifierTimeoutError"}:
        timed_out = True

    return {
        "task_id": task_name,
        "trial_name": trial_name,
        "trial_dir": trial_dir,
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "execution_time_seconds": _duration_seconds(agent_exec_started, agent_exec_finished)
        or _duration_seconds(payload.get("started_at"), payload.get("finished_at")),
        "verifier_started_at": verifier_started,
        "verifier_finished_at": verifier_finished,
        "reward": reward,
        "passed": passed,
        "timed_out": timed_out,
        "usage": {
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "cache_tokens": cache_tokens,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "cost_usd": _to_float(agent_result.get("cost_usd"), default=0.0),
            "requests": 1,
        },
        "llm_rounds": llm_rounds,
        "transcript_length": _extract_transcript_length(trial_dir),
        "error": error_payload,
        "verifier": {
            "reward": reward,
            "returncode": None,
            "notes": exception_info.get("exception_message") if exception_info else "",
            "feedback": [],
            "stdout_path": str(trial_dir / "verifier" / "test-stdout.txt"),
            "stderr_path": str(trial_dir / "verifier" / "test-stderr.txt"),
            "ctrf_path": str(trial_dir / "verifier" / "ctrf.json"),
            "reward_path": reward_path,
            "timed_out": timed_out,
            "timeout_sec": None,
            "timeout_message": exception_info.get("exception_message") if timed_out else "",
            "started_at": verifier_started,
            "finished_at": verifier_finished,
        },
        "intra_attempt_early_stop": intra_attempt_early_stop,
    }


def _sort_trials(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    max_dt = datetime.max.replace(tzinfo=timezone.utc)

    def key(item: dict[str, Any]) -> tuple[datetime, str]:
        started = _parse_dt(item.get("started_at")) or max_dt
        return started, str(item.get("trial_name") or "")

    return sorted(entries, key=key)


def _aggregate_usage(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    agg = {
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "cost_usd": 0.0,
        "requests": 0,
    }
    for attempt in attempts:
        usage = ((attempt.get("execution") or {}).get("usage") or {})
        agg["total_tokens"] += _to_int(usage.get("total_tokens"), default=0)
        agg["prompt_tokens"] += _to_int(usage.get("prompt_tokens"), default=0)
        agg["completion_tokens"] += _to_int(usage.get("completion_tokens"), default=0)
        agg["input_tokens"] += _to_int(usage.get("input_tokens"), default=0)
        agg["output_tokens"] += _to_int(usage.get("output_tokens"), default=0)
        agg["cache_tokens"] += _to_int(usage.get("cache_tokens"), default=0)
        agg["cache_read_tokens"] += _to_int(usage.get("cache_read_tokens"), default=0)
        agg["cache_write_tokens"] += _to_int(usage.get("cache_write_tokens"), default=0)
        agg["cost_usd"] += _to_float(usage.get("cost_usd"), default=0.0)
        agg["requests"] += _to_int(usage.get("requests"), default=0)
    agg["cost_usd"] = round(agg["cost_usd"], 8)
    return agg


def _build_efficiency(tasks: list[dict[str, Any]], max_task_attempts: int) -> dict[str, Any]:
    n_tasks = len(tasks)
    total_tokens = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_tokens = 0
    total_cache_read_tokens = 0
    total_cache_write_tokens = 0
    total_cost_usd = 0.0
    total_requests = 0
    total_execution_time = 0.0
    tasks_with_usage_data = 0
    success_count = 0

    per_task: list[dict[str, Any]] = []
    for task in tasks:
        usage = task.get("usage") or {}
        task_tokens = _to_int(usage.get("total_tokens"), default=0)
        task_cost = _to_float(usage.get("cost_usd"), default=0.0)
        task_has_usage = task_tokens > 0 or task_cost > 0
        if task_has_usage:
            tasks_with_usage_data += 1

        total_tokens += task_tokens
        total_input_tokens += _to_int(usage.get("input_tokens"), default=0)
        total_output_tokens += _to_int(usage.get("output_tokens"), default=0)
        total_cache_tokens += _to_int(usage.get("cache_tokens"), default=0)
        total_cache_read_tokens += _to_int(usage.get("cache_read_tokens"), default=0)
        total_cache_write_tokens += _to_int(usage.get("cache_write_tokens"), default=0)
        total_cost_usd += task_cost
        total_requests += _to_int(usage.get("requests"), default=0)
        total_execution_time += _to_float(task.get("execution_time"), default=0.0)

        first_success_attempt = task.get("first_success_attempt")
        task_success = first_success_attempt is not None
        if task_success:
            success_count += 1

        per_task.append(
            {
                "task_id": task.get("task_id"),
                "success": task_success,
                "first_success_attempt": first_success_attempt,
                "attempt_count": task.get("attempt_count"),
                "total_tokens": task_tokens,
                "cost_usd": round(task_cost, 8),
            }
        )

    success_rate = (success_count / n_tasks) if n_tasks else 0.0
    success_at_k: dict[str, float] = {}
    for k in range(1, max(1, max_task_attempts) + 1):
        succeeded = 0
        for task in tasks:
            first_success_attempt = task.get("first_success_attempt")
            if first_success_attempt is not None and int(first_success_attempt) <= k:
                succeeded += 1
        success_at_k[str(k)] = round((succeeded / n_tasks) if n_tasks else 0.0, 6)

    tokens_per_task = (total_tokens / n_tasks) if n_tasks else 0.0
    cost_per_task = (total_cost_usd / n_tasks) if n_tasks else 0.0

    score_total = float(success_count)
    score_per_1k_tokens = (score_total / (total_tokens / 1000.0)) if total_tokens > 0 else None
    score_per_dollar = (score_total / total_cost_usd) if total_cost_usd > 0 else None

    return {
        "total_tokens": total_tokens,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cache_tokens": total_cache_tokens,
        "total_cache_read_tokens": total_cache_read_tokens,
        "total_cache_write_tokens": total_cache_write_tokens,
        "total_cost_usd": round(total_cost_usd, 8),
        "total_requests": total_requests,
        "total_execution_time_seconds": round(total_execution_time, 6),
        "tasks_with_usage_data": tasks_with_usage_data,
        "tokens_per_task": round(tokens_per_task, 3),
        "cost_per_task_usd": round(cost_per_task, 8),
        "score_per_1k_tokens": round(score_per_1k_tokens, 8) if score_per_1k_tokens is not None else None,
        "score_per_dollar": round(score_per_dollar, 8) if score_per_dollar is not None else None,
        "success_rate": round(success_rate, 6),
        "success_per_1k_tokens": round((success_count / (total_tokens / 1000.0)), 8) if total_tokens > 0 else None,
        "success_per_dollar": round((success_count / total_cost_usd), 8) if total_cost_usd > 0 else None,
        "success_at_k": success_at_k,
        "per_task": per_task,
    }


def main() -> None:
    args = parse_args()
    job_dir = args.jobs_root / args.job_name
    if not job_dir.exists():
        raise SystemExit(f"SkillsBench job directory not found: {job_dir}")

    trial_dirs = sorted(
        [path for path in job_dir.iterdir() if path.is_dir() and (path / "result.json").exists()],
        key=lambda item: item.name,
    )
    if not trial_dirs:
        raise SystemExit(f"No trial result.json found in job directory: {job_dir}")

    trials_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trial_dir in trial_dirs:
        entry = _extract_trial_entry(trial_dir)
        if entry is None:
            continue
        trials_by_task[entry["task_id"]].append(entry)

    retry_policies = {
        "feedback_policy": args.feedback_policy,
        "feedback_format": args.feedback_format,
        "feedback_strategy": args.feedback_strategy,
        "feedback_answer_safety": args.feedback_answer_safety,
        "stop_rule": args.stop_rule,
        "stop_threshold": args.stop_threshold,
        "early_stop_intra_attempt": args.early_stop_intra_attempt,
    }

    tasks: list[dict[str, Any]] = []
    for task_id in sorted(trials_by_task.keys()):
        sorted_trials = _sort_trials(trials_by_task[task_id])
        attempt_records: list[dict[str, Any]] = []
        previous_reward = 0.0
        previous_transcript_length = 0

        first_success_attempt: int | None = None
        for idx, trial in enumerate(sorted_trials, start=1):
            passed = bool(trial["passed"])
            if passed and first_success_attempt is None:
                first_success_attempt = idx

            transcript_length = _to_int(trial.get("transcript_length"), default=0)
            reward = _to_float(trial.get("reward"), default=0.0)
            usage = dict(trial["usage"])

            attempt_records.append(
                {
                    "attempt": idx,
                    "started_at": trial.get("started_at"),
                    "finished_at": trial.get("finished_at"),
                    "feedback_prompt": None,
                    "feedback_prompt_stats": {"chars": 0, "tokens_estimate": 0},
                    "feedback_policy": args.feedback_policy,
                    "feedback_format": args.feedback_format,
                    "feedback_strategy": args.feedback_strategy,
                    "execution": {
                        "llm_rounds": trial.get("llm_rounds"),
                        "usage": usage,
                        "usage_per_round": [],
                        "execution_time": _to_float(trial.get("execution_time_seconds"), default=0.0),
                        "agent_dir": str(trial["trial_dir"] / "agent"),
                        "error": trial.get("error") or {},
                        "intra_attempt_early_stop": bool(trial.get("intra_attempt_early_stop")),
                    },
                    "verifier": trial.get("verifier") or {},
                    "grading": {
                        "score": reward,
                        "max_score": 1.0,
                        "passed": passed,
                        "criteria": [
                            {
                                "criterion": "overall",
                                "score": reward,
                                "max_score": 1.0,
                            }
                        ],
                    },
                    "transcript_length": transcript_length,
                    "transcript_length_delta": transcript_length - previous_transcript_length,
                    "score_delta": round(reward - previous_reward, 6),
                    "unresolved_criteria_count": 0 if passed else 1,
                    "stop_rule": args.stop_rule,
                    "stop_rule_threshold": args.stop_threshold,
                    "stop_rule_triggered": passed,
                    "stop_rule_trigger_reason": "reward-maxed" if passed else None,
                }
            )

            previous_reward = reward
            previous_transcript_length = transcript_length

        aggregated_usage = _aggregate_usage(attempt_records)
        total_execution_time = sum(
            _to_float(((attempt.get("execution") or {}).get("execution_time")), default=0.0)
            for attempt in attempt_records
        )
        total_llm_rounds = sum(
            _to_int(((attempt.get("execution") or {}).get("llm_rounds")), default=0)
            for attempt in attempt_records
        )
        final_grading = (attempt_records[-1].get("grading") if attempt_records else {}) or {}
        success_within_budget = first_success_attempt is not None

        tasks.append(
            {
                "task_id": task_id,
                "task_prompt": None,
                "status": "passed" if success_within_budget else "failed",
                "timed_out": any(((attempt.get("verifier") or {}).get("timed_out")) for attempt in attempt_records),
                "execution_time": round(total_execution_time, 6),
                "transcript_length": sum(_to_int(attempt.get("transcript_length"), default=0) for attempt in attempt_records),
                "llm_rounds": total_llm_rounds,
                "usage": aggregated_usage,
                "usage_per_round": [],
                "workspace": {},
                "grading": final_grading,
                "grading_summary": {
                    "score": final_grading.get("score"),
                    "max_score": final_grading.get("max_score"),
                    "passed": bool(final_grading.get("passed")),
                },
                "completion": {"passed": success_within_budget},
                "frontmatter": {},
                "attempt_count": len(attempt_records),
                "first_success_attempt": first_success_attempt,
                "success_within_budget": success_within_budget,
                "unresolved_criteria_count_by_attempt": [
                    attempt.get("unresolved_criteria_count") for attempt in attempt_records
                ],
                "transcript_length_by_attempt": [
                    _to_int(attempt.get("transcript_length"), default=0) for attempt in attempt_records
                ],
                "prompt_tokens_by_attempt": [
                    _to_int(((attempt.get("execution") or {}).get("usage") or {}).get("prompt_tokens"), default=0)
                    for attempt in attempt_records
                ],
                "completion_tokens_by_attempt": [
                    _to_int(((attempt.get("execution") or {}).get("usage") or {}).get("completion_tokens"), default=0)
                    for attempt in attempt_records
                ],
                "feedback_length_chars_by_attempt": [0 for _ in attempt_records],
                "stop_reason": "succeeded" if success_within_budget else "max-attempts-reached",
                "attempts": attempt_records,
                "retry_policies": retry_policies,
                "judge_usage": {},
                "workspace_changed_by_attempt": [False for _ in attempt_records],
                "source_job": str(job_dir),
                "source_trial": sorted_trials[0]["trial_name"] if sorted_trials else None,
            }
        )

    success_first_attempt = 0
    for task in tasks:
        if task.get("first_success_attempt") == 1:
            success_first_attempt += 1

    retry_metrics = {
        "first_attempt_success_rate": round((success_first_attempt / len(tasks)) if tasks else 0.0, 6),
        "average_attempts_executed": round(
            (sum(_to_int(task.get("attempt_count"), default=0) for task in tasks) / len(tasks)) if tasks else 0.0,
            6,
        ),
    }

    payload = {
        "model": args.model,
        "benchmark_version": args.benchmark_version,
        "run_id": args.run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "suite": args.suite,
        "runs_per_task": 1,
        "max_task_attempts": max(1, args.max_task_attempts),
        "retry_policies": retry_policies,
        "tasks": tasks,
        "efficiency": _build_efficiency(tasks, max(1, args.max_task_attempts)),
        "retry_metrics": retry_metrics,
        "source": {
            "jobs_root": str(args.jobs_root),
            "job_filter": args.job_name,
            "agent": args.agent,
            "trial_count": len(trial_dirs),
            "sandbox": args.sandbox,
            "mode": args.mode,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote aggregated SkillsBench result: {args.output}")


if __name__ == "__main__":
    main()
