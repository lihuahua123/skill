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


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_text(path: Path, limit: int = 4000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _existing_path_str(path: Path) -> str:
    return str(path) if path.exists() else ""


def _load_reward_from_path(path: Path) -> float | None:
    if not path.exists():
        return None
    if path.suffix == ".txt":
        try:
            return float(path.read_text(encoding="utf-8").strip())
        except Exception:
            return None
    if path.suffix == ".json":
        payload = _read_json(path)
        if isinstance(payload, dict):
            if "reward" in payload:
                return _to_float(payload.get("reward"), default=0.0)
            for value in payload.values():
                try:
                    return float(value)
                except Exception:
                    continue
    return None


def _load_reward_from_file(trial_dir: Path) -> float | None:
    for candidate in (
        trial_dir / "verifier" / "reward.txt",
        trial_dir / "verifier" / "reward.json",
    ):
        reward = _load_reward_from_path(candidate)
        if reward is not None:
            return reward
    return None


def _extract_reward_from_verifier_result(verifier_result: dict[str, Any]) -> float | None:
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
    if isinstance(rewards, (float, int)):
        return float(rewards)
    return None


def _extract_reward(payload: dict[str, Any], trial_dir: Path) -> float:
    verifier_result = _as_dict(payload.get("verifier_result"))
    reward = _extract_reward_from_verifier_result(verifier_result)
    if reward is not None:
        return reward
    fallback = _load_reward_from_file(trial_dir)
    if fallback is not None:
        return fallback
    return 0.0


def _extract_trajectory_payload(trial_dir: Path) -> dict[str, Any]:
    payload = _read_json(trial_dir / "agent" / "trajectory.json")
    return payload if isinstance(payload, dict) else {}


def _extract_transcript_length(trial_dir: Path) -> int:
    steps = _as_list(_extract_trajectory_payload(trial_dir).get("steps"))
    return len(steps)


def _extract_agent_session_id(attempt_payload: dict[str, Any], trial_dir: Path) -> str | None:
    direct = attempt_payload.get("agent_session_id")
    if isinstance(direct, str) and direct:
        return direct

    agent_result = _as_dict(attempt_payload.get("agent_result"))
    metadata = _as_dict(agent_result.get("metadata"))
    for key in ("session_id", "agent_session_id", "conversation_id", "thread_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value

    trajectory_payload = _extract_trajectory_payload(trial_dir)
    session_id = trajectory_payload.get("session_id")
    if isinstance(session_id, str) and session_id:
        return session_id
    return None


def _extract_usage(agent_result: dict[str, Any]) -> dict[str, Any]:
    prompt_tokens = _to_int(agent_result.get("n_input_tokens"), default=0)
    completion_tokens = _to_int(agent_result.get("n_output_tokens"), default=0)
    cache_tokens = _to_int(agent_result.get("n_cache_tokens"), default=0)
    total_tokens = prompt_tokens + completion_tokens
    if total_tokens <= 0 and cache_tokens > 0:
        total_tokens = cache_tokens
    return {
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
    }


def _extract_llm_rounds(agent_result: dict[str, Any]) -> int:
    metadata = _as_dict(agent_result.get("metadata"))
    llm_rounds = metadata.get("n_episodes")
    if llm_rounds is None:
        llm_rounds = metadata.get("n_rounds")
    return _to_int(llm_rounds, default=0)


def _extract_error_payload(exception_info: dict[str, Any]) -> dict[str, Any]:
    if not exception_info:
        return {}
    return {
        "exception_type": exception_info.get("exception_type"),
        "exception_message": exception_info.get("exception_message"),
        "exception_traceback": exception_info.get("exception_traceback"),
        "occurred_at": exception_info.get("occurred_at"),
    }


def _extract_feedback_items_from_ctrf(ctrf_path: Path) -> list[str]:
    payload = _read_json(ctrf_path)
    if not isinstance(payload, dict):
        return []

    feedback_items: list[str] = []
    results = _as_dict(payload.get("results"))
    tests = _as_list(results.get("tests"))
    for test in tests:
        if not isinstance(test, dict):
            continue
        status = str(test.get("status") or "").lower()
        if status not in {"failed", "broken"}:
            continue

        name = str(test.get("name") or test.get("test") or test.get("title") or "").strip()
        message_parts: list[str] = []
        for key in ("message", "rawMessage", "trace", "output"):
            value = test.get(key)
            if isinstance(value, str) and value.strip():
                message_parts.append(value.strip())
                break

        item = name
        if message_parts:
            item = f"{item}: {message_parts[0]}" if item else message_parts[0]
        item = item.strip()
        if item:
            feedback_items.append(item)

    return feedback_items[:20]


def _extract_failed_reasons(trial_dir: Path) -> list[str]:
    path = trial_dir / "verifier" / "failed_reasons.txt"
    if not path.exists():
        return []
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]
    return [line for line in lines if line][:20]


_NOISE_PREFIXES = (
    "Hit:",
    "Get:",
    "Ign:",
    "Fetched ",
    "Reading package lists",
    "Building dependency tree",
    "Reading state information",
    "curl is already the newest version",
    "0 upgraded,",
    "Selecting previously unselected",
)

_ERROR_MARKERS = (
    "error:",
    "failed",
    "not found",
    "no such file",
    "command not found",
    "traceback",
    "exception",
    "assertionerror",
    "modulenotfounderror",
    "filenotfounderror",
    "curl:",
)


def _extract_error_lines(text: str, *, limit: int = 8) -> list[str]:
    items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if any(lower.startswith(prefix.lower()) for prefix in _NOISE_PREFIXES):
            continue
        if any(marker in lower for marker in _ERROR_MARKERS):
            items.append(line)
    return items[:limit]


def _is_noise_line(text: str) -> bool:
    line = text.strip()
    if not line:
        return True
    lower = line.lower()
    return any(lower.startswith(prefix.lower()) for prefix in _NOISE_PREFIXES)


def _has_meaningful_error_text(text: str) -> bool:
    line = text.strip().lower()
    if not line:
        return False
    if _is_noise_line(line):
        return False
    return any(marker in line for marker in _ERROR_MARKERS)


def _is_low_signal_feedback(feedback_items: list[str]) -> bool:
    if not feedback_items:
        return True
    return all(_is_noise_line(item) for item in feedback_items if isinstance(item, str))


def _summarize_verifier_logs(stdout_path: str, stderr_path: str) -> tuple[list[str], str]:
    stderr_text = _read_text(Path(stderr_path), limit=4000) if stderr_path else ""
    stdout_text = _read_text(Path(stdout_path), limit=4000) if stdout_path else ""

    stderr_items = _extract_error_lines(stderr_text)
    if stderr_items:
        return stderr_items[:5], "\n".join(stderr_items[:5])

    stdout_items = _extract_error_lines(stdout_text)
    if stdout_items:
        return stdout_items[:5], "\n".join(stdout_items[:5])

    for text in (stderr_text, stdout_text):
        if not text.strip():
            continue
        non_empty_lines = [line.strip() for line in text.splitlines() if line.strip()]
        if non_empty_lines:
            tail = "\n".join(non_empty_lines[-5:])
            return [], tail

    return [], ""


def _build_verifier_payload(
    verifier_result: dict[str, Any],
    trial_dir: Path,
    exception_info: dict[str, Any],
    fallback_reward: float,
    verifier_started_at: Any,
    verifier_finished_at: Any,
) -> dict[str, Any]:
    stdout_path = verifier_result.get("stdout_path") or _existing_path_str(trial_dir / "verifier" / "test-stdout.txt")
    stderr_path = verifier_result.get("stderr_path") or _existing_path_str(trial_dir / "verifier" / "test-stderr.txt")
    ctrf_path = verifier_result.get("ctrf_path") or _existing_path_str(trial_dir / "verifier" / "ctrf.json")
    reward_path = verifier_result.get("reward_path")
    if not isinstance(reward_path, str) or not reward_path:
        if (trial_dir / "verifier" / "reward.txt").exists():
            reward_path = str(trial_dir / "verifier" / "reward.txt")
        elif (trial_dir / "verifier" / "reward.json").exists():
            reward_path = str(trial_dir / "verifier" / "reward.json")
        else:
            reward_path = ""

    reward = _extract_reward_from_verifier_result(verifier_result)
    if reward is None:
        reward = fallback_reward
    reward = max(0.0, min(1.0, reward))

    feedback_items = verifier_result.get("feedback_items")
    if not isinstance(feedback_items, list):
        feedback_items = []
    if not feedback_items:
        feedback_items = _extract_feedback_items_from_ctrf(Path(ctrf_path)) if ctrf_path else []
    if not feedback_items:
        feedback_items = _extract_failed_reasons(trial_dir)

    log_feedback_items, log_notes = _summarize_verifier_logs(stdout_path, stderr_path)
    if _is_low_signal_feedback(feedback_items) and log_feedback_items:
        feedback_items = log_feedback_items

    notes = verifier_result.get("notes")
    if not isinstance(notes, str):
        notes = ""
    if (not notes.strip()) or (not _has_meaningful_error_text(notes) and log_notes):
        if exception_info and exception_info.get("exception_message"):
            notes = str(exception_info.get("exception_message") or "")
        elif log_notes:
            notes = log_notes
        elif not feedback_items:
            notes = f"reward={reward}"
        else:
            notes = ""

    exception_type = str(exception_info.get("exception_type") or "")
    timed_out = exception_type in {"AgentTimeoutError", "VerifierTimeoutError"}

    return {
        "reward": reward,
        "returncode": None,
        "notes": notes,
        "feedback": feedback_items,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "ctrf_path": ctrf_path,
        "reward_path": reward_path,
        "timed_out": timed_out,
        "timeout_sec": None,
        "timeout_message": exception_info.get("exception_message") if timed_out else "",
        "started_at": verifier_started_at,
        "finished_at": verifier_finished_at,
    }


def _build_attempt_record(
    *,
    attempt_number: int,
    trial_dir: Path,
    attempt_payload: dict[str, Any],
    attempt_started_at: Any,
    attempt_finished_at: Any,
    reward: float,
    passed: bool,
    usage: dict[str, Any],
    llm_rounds: int,
    execution_time_seconds: float,
    transcript_length: int,
    error_payload: dict[str, Any],
    verifier_payload: dict[str, Any],
    retry_policies: dict[str, Any],
    previous_reward: float,
    previous_transcript_length: int,
    intra_attempt_early_stop: bool,
) -> dict[str, Any]:
    feedback_prompt = attempt_payload.get("feedback_prompt")
    if not isinstance(feedback_prompt, str):
        feedback_prompt = None
    feedback_length = len(feedback_prompt) if feedback_prompt else 0

    agent_session_id = _extract_agent_session_id(attempt_payload, trial_dir)
    feedback_items = verifier_payload.get("feedback") or []
    unresolved_criteria_count = 0 if passed else max(1, len(feedback_items) or 0)

    stop_rule_triggered = bool(passed)
    stop_rule_trigger_reason = "reward-maxed" if passed else None

    return {
        "attempt": attempt_number,
        "instruction_kind": attempt_payload.get("instruction_kind"),
        "started_at": attempt_started_at,
        "finished_at": attempt_finished_at,
        "feedback_prompt": feedback_prompt,
        "feedback_prompt_stats": {
            "chars": feedback_length,
            "tokens_estimate": feedback_length // 4 if feedback_length else 0,
        },
        "feedback_policy": retry_policies.get("feedback_policy"),
        "feedback_format": retry_policies.get("feedback_format"),
        "feedback_strategy": retry_policies.get("feedback_strategy"),
        "agent_session_id": agent_session_id,
        "execution": {
            "llm_rounds": llm_rounds,
            "usage": usage,
            "usage_per_round": [],
            "execution_time": execution_time_seconds,
            "agent_dir": str(trial_dir / "agent"),
            "error": error_payload,
            "intra_attempt_early_stop": intra_attempt_early_stop,
        },
        "verifier": verifier_payload,
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
        "unresolved_criteria_count": unresolved_criteria_count,
        "stop_rule": retry_policies.get("stop_rule"),
        "stop_rule_threshold": retry_policies.get("stop_threshold"),
        "stop_rule_triggered": stop_rule_triggered,
        "stop_rule_trigger_reason": stop_rule_trigger_reason,
    }


def _build_legacy_attempt_records(
    sorted_trials: list[dict[str, Any]],
    retry_policies: dict[str, Any],
) -> list[dict[str, Any]]:
    attempt_records: list[dict[str, Any]] = []
    previous_reward = 0.0
    previous_transcript_length = 0

    for idx, trial in enumerate(sorted_trials, start=1):
        reward = _to_float(trial.get("reward"), default=0.0)
        passed = bool(trial.get("passed"))
        transcript_length = _to_int(trial.get("transcript_length"), default=0)
        attempt_records.append(
            _build_attempt_record(
                attempt_number=idx,
                trial_dir=trial["trial_dir"],
                attempt_payload={},
                attempt_started_at=trial.get("started_at"),
                attempt_finished_at=trial.get("finished_at"),
                reward=reward,
                passed=passed,
                usage=dict(trial.get("usage") or {}),
                llm_rounds=_to_int(trial.get("llm_rounds"), default=0),
                execution_time_seconds=_to_float(trial.get("execution_time_seconds"), default=0.0),
                transcript_length=transcript_length,
                error_payload=trial.get("error") or {},
                verifier_payload=trial.get("verifier") or {},
                retry_policies=retry_policies,
                previous_reward=previous_reward,
                previous_transcript_length=previous_transcript_length,
                intra_attempt_early_stop=bool(trial.get("intra_attempt_early_stop")),
            )
        )
        previous_reward = reward
        previous_transcript_length = transcript_length

    return attempt_records


def _extract_trial_entry(trial_dir: Path) -> dict[str, Any] | None:
    payload = _read_json(trial_dir / "result.json")
    if not isinstance(payload, dict):
        return None

    task_name = str(payload.get("task_name") or trial_dir.name.split("__")[0])
    trial_name = str(payload.get("trial_name") or trial_dir.name)
    agent_result = _as_dict(payload.get("agent_result"))
    verifier_result = _as_dict(payload.get("verifier_result"))
    exception_info = _as_dict(payload.get("exception_info"))

    verifier_timing = _as_dict(payload.get("verifier"))
    agent_exec_timing = _as_dict(payload.get("agent_execution"))

    verifier_started = verifier_timing.get("started_at")
    verifier_finished = verifier_timing.get("finished_at")
    agent_exec_started = agent_exec_timing.get("started_at")
    agent_exec_finished = agent_exec_timing.get("finished_at")

    reward = max(0.0, min(1.0, _extract_reward(payload, trial_dir)))
    passed = reward >= 1.0
    error_payload = _extract_error_payload(exception_info)
    exception_type = str(exception_info.get("exception_type") or "")
    intra_attempt_early_stop = exception_type == "IntraAttemptEarlyStop" or (trial_dir / "early_stop.json").exists()

    verifier_payload = _build_verifier_payload(
        verifier_result=verifier_result,
        trial_dir=trial_dir,
        exception_info=exception_info,
        fallback_reward=reward,
        verifier_started_at=verifier_started,
        verifier_finished_at=verifier_finished,
    )

    return {
        "task_id": task_name,
        "trial_name": trial_name,
        "trial_dir": trial_dir,
        "payload": payload,
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "execution_time_seconds": _duration_seconds(agent_exec_started, agent_exec_finished)
        or _duration_seconds(payload.get("started_at"), payload.get("finished_at")),
        "reward": reward,
        "passed": passed,
        "usage": _extract_usage(agent_result),
        "llm_rounds": _extract_llm_rounds(agent_result),
        "transcript_length": _extract_transcript_length(trial_dir),
        "error": error_payload,
        "verifier": verifier_payload,
        "intra_attempt_early_stop": intra_attempt_early_stop,
        "attempt_count": _to_int(payload.get("attempt_count"), default=0),
        "first_success_attempt": payload.get("first_success_attempt"),
        "stop_reason": payload.get("stop_reason"),
        "agent_session_id": _extract_agent_session_id(payload, trial_dir),
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


def _build_attempt_records_from_internal_attempts(
    trial: dict[str, Any],
    retry_policies: dict[str, Any],
) -> tuple[list[dict[str, Any]], int | None, str | None]:
    payload = _as_dict(trial.get("payload"))
    internal_attempts = _as_list(payload.get("attempts"))
    if not internal_attempts:
        return [], None, None

    trial_dir = trial["trial_dir"]
    attempts: list[dict[str, Any]] = []
    previous_reward = 0.0
    previous_transcript_length = 0

    for fallback_idx, raw_attempt in enumerate(internal_attempts, start=1):
        if not isinstance(raw_attempt, dict):
            continue

        attempt_payload = dict(raw_attempt)
        attempt_number = _to_int(attempt_payload.get("attempt"), default=fallback_idx)
        agent_result = _as_dict(attempt_payload.get("agent_result"))
        verifier_result = _as_dict(attempt_payload.get("verifier_result"))
        attempt_reward = _extract_reward_from_verifier_result(verifier_result)

        if attempt_reward is None:
            if fallback_idx == len(internal_attempts):
                attempt_reward = _to_float(trial.get("reward"), default=0.0)
            else:
                attempt_reward = 0.0
        attempt_reward = max(0.0, min(1.0, attempt_reward))
        passed = attempt_reward >= 1.0

        attempt_started_at = attempt_payload.get("started_at") or trial.get("started_at")
        attempt_finished_at = attempt_payload.get("finished_at") or trial.get("finished_at")
        execution_time_seconds = _duration_seconds(attempt_started_at, attempt_finished_at)
        usage = _extract_usage(agent_result)
        llm_rounds = _extract_llm_rounds(agent_result)

        verifier_payload = _build_verifier_payload(
            verifier_result=verifier_result,
            trial_dir=trial_dir,
            exception_info={},
            fallback_reward=attempt_reward,
            verifier_started_at=attempt_finished_at,
            verifier_finished_at=attempt_finished_at,
        )

        # Internal attempts currently do not expose per-attempt trajectory slices.
        # Keep the task-level trajectory length on the final attempt as the best available proxy.
        transcript_length = _to_int(trial.get("transcript_length"), default=0) if fallback_idx == len(internal_attempts) else 0

        attempts.append(
            _build_attempt_record(
                attempt_number=attempt_number,
                trial_dir=trial_dir,
                attempt_payload=attempt_payload,
                attempt_started_at=attempt_started_at,
                attempt_finished_at=attempt_finished_at,
                reward=attempt_reward,
                passed=passed,
                usage=usage,
                llm_rounds=llm_rounds,
                execution_time_seconds=execution_time_seconds,
                transcript_length=transcript_length,
                error_payload={},
                verifier_payload=verifier_payload,
                retry_policies=retry_policies,
                previous_reward=previous_reward,
                previous_transcript_length=previous_transcript_length,
                intra_attempt_early_stop=False,
            )
        )
        previous_reward = attempt_reward
        previous_transcript_length = transcript_length

    first_success_attempt = payload.get("first_success_attempt")
    if first_success_attempt is None:
        for attempt in attempts:
            if bool(((attempt.get("grading") or {}).get("passed"))):
                first_success_attempt = attempt.get("attempt")
                break

    stop_reason = payload.get("stop_reason")
    return attempts, _to_int(first_success_attempt, default=0) or None, stop_reason if isinstance(stop_reason, str) else None


def _build_task_record(
    task_id: str,
    sorted_trials: list[dict[str, Any]],
    retry_policies: dict[str, Any],
    job_dir: Path,
) -> dict[str, Any]:
    primary_trial = sorted_trials[0]
    internal_attempts, internal_first_success_attempt, internal_stop_reason = _build_attempt_records_from_internal_attempts(
        primary_trial,
        retry_policies,
    )

    if internal_attempts:
        attempt_records = internal_attempts
        first_success_attempt = internal_first_success_attempt
        stop_reason = internal_stop_reason or ("succeeded" if first_success_attempt is not None else "max-attempts-reached")
        source_trial = primary_trial["trial_name"]
    else:
        attempt_records = _build_legacy_attempt_records(sorted_trials, retry_policies)
        first_success_attempt = None
        for attempt in attempt_records:
            if bool(((attempt.get("grading") or {}).get("passed"))):
                first_success_attempt = _to_int(attempt.get("attempt"), default=0) or None
                break
        stop_reason = "succeeded" if first_success_attempt is not None else "max-attempts-reached"
        source_trial = sorted_trials[0]["trial_name"] if sorted_trials else None

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

    return {
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
        "feedback_length_chars_by_attempt": [
            _to_int(((attempt.get("feedback_prompt_stats") or {}).get("chars")), default=0)
            for attempt in attempt_records
        ],
        "stop_reason": stop_reason,
        "attempts": attempt_records,
        "retry_policies": retry_policies,
        "judge_usage": {},
        "workspace_changed_by_attempt": [False for _ in attempt_records],
        "source_job": str(job_dir),
        "source_trial": source_trial,
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
        tasks.append(_build_task_record(task_id, sorted_trials, retry_policies, job_dir))

    success_first_attempt = sum(1 for task in tasks if task.get("first_success_attempt") == 1)
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
