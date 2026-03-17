"""
PinchBench grading engine.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib_agent import ensure_agent_exists, run_openclaw_prompt, slugify_model
from lib_tasks import Task


logger = logging.getLogger(__name__)


DEFAULT_JUDGE_MODEL = "openrouter/anthropic/claude-opus-4.5"
DEFAULT_JUDGE_AGENT_PREFIX = "bench-judge"
DEFAULT_JUDGE_TIMEOUT_SECONDS = 180

# Kimi (Moonshot) judge defaults; override with env PINCHBENCH_KIMI_JUDGE_API_KEY in production
KIMI_JUDGE_API_BASE = "https://api.moonshot.cn/v1"
KIMI_JUDGE_MODEL = "kimi-k2.5"
# Default key for development; prefer env PINCHBENCH_KIMI_JUDGE_API_KEY
KIMI_JUDGE_API_KEY_DEFAULT = "sk-ccNgMEVLZvvhMAgMVl8H7l3YHUlwUjelCGeDDZWR1vpTS3jh"
# Kimi K2.5 pricing USD per 1M tokens (input $0.60, output $2.00)
KIMI_JUDGE_PRICE_INPUT_PER_1M = 0.60
KIMI_JUDGE_PRICE_OUTPUT_PER_1M = 2.00
KIMI_JUDGE_MAX_RETRIES = 3


def _is_retryable_kimi_error(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or 500 <= exc.code < 600
    return isinstance(exc, urllib.error.URLError)


@dataclass
class GradeResult:
    task_id: str
    score: float
    max_score: float
    grading_type: str
    breakdown: Dict[str, float]
    notes: str
    judge_usage: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "task_id": self.task_id,
            "score": self.score,
            "max_score": self.max_score,
            "grading_type": self.grading_type,
            "breakdown": self.breakdown,
            "notes": self.notes,
        }
        if self.judge_usage is not None:
            d["judge_usage"] = self.judge_usage
        return d


def grade_task(
    *,
    task: Task,
    execution_result: Dict[str, Any],
    skill_dir: Path,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    judge_agent_prefix: str = DEFAULT_JUDGE_AGENT_PREFIX,
    judge_timeout_seconds: float = DEFAULT_JUDGE_TIMEOUT_SECONDS,
    judge_api_base: Optional[str] = None,
    judge_api_model: Optional[str] = None,
    judge_api_key: Optional[str] = None,
    verbose: bool = False,
) -> GradeResult:
    grading_type = task.grading_type
    if verbose:
        logger.info("   [VERBOSE] Grading task %s with type: %s", task.task_id, grading_type)
        logger.info("   [VERBOSE] Execution status: %s", execution_result.get("status", "unknown"))

    use_kimi_judge = (
        judge_api_base is not None
        and judge_api_model is not None
        and judge_api_key is not None
    )

    if grading_type == "automated":
        result = _grade_automated(task, execution_result, verbose=verbose)
        if verbose:
            logger.info("   [VERBOSE] Automated grade breakdown: %s", result.breakdown)
        return result
    if grading_type == "llm_judge":
        if use_kimi_judge:
            result = _grade_llm_judge_kimi(
                task=task,
                execution_result=execution_result,
                api_base=judge_api_base,
                model=judge_api_model,
                api_key=judge_api_key,
                timeout_seconds=judge_timeout_seconds,
                verbose=verbose,
            )
        else:
            result = _grade_llm_judge(
                task=task,
                execution_result=execution_result,
                judge_model=judge_model,
                judge_agent_prefix=judge_agent_prefix,
                judge_timeout_seconds=judge_timeout_seconds,
                skill_dir=skill_dir,
                verbose=verbose,
            )
        if verbose:
            logger.info("   [VERBOSE] LLM judge breakdown: %s", result.breakdown)
        return result
    if grading_type == "hybrid":
        auto_result = _grade_automated(task, execution_result, verbose=verbose)
        if use_kimi_judge:
            llm_result = _grade_llm_judge_kimi(
                task=task,
                execution_result=execution_result,
                api_base=judge_api_base,
                model=judge_api_model,
                api_key=judge_api_key,
                timeout_seconds=judge_timeout_seconds,
                verbose=verbose,
            )
        else:
            llm_result = _grade_llm_judge(
                task=task,
                execution_result=execution_result,
                judge_model=judge_model,
                judge_agent_prefix=judge_agent_prefix,
                judge_timeout_seconds=judge_timeout_seconds,
                skill_dir=skill_dir,
                verbose=verbose,
            )
        return _combine_grades(task, auto_result, llm_result)
    raise ValueError(f"Unknown grading type: {grading_type}")


def _grade_automated(task: Task, execution_result: Dict[str, Any], verbose: bool = False) -> GradeResult:
    grading_code = _extract_grading_code(task)
    if not grading_code:
        return GradeResult(
            task_id=task.task_id,
            score=0.0,
            max_score=1.0,
            grading_type="automated",
            breakdown={},
            notes="No automated grading code found",
        )

    namespace: Dict[str, Any] = {}
    exec(grading_code, namespace)
    grade_func = namespace.get("grade")
    if not callable(grade_func):
        return GradeResult(
            task_id=task.task_id,
            score=0.0,
            max_score=1.0,
            grading_type="automated",
            breakdown={},
            notes="Automated grading function missing",
        )

    scores = grade_func(
        execution_result.get("transcript", []),
        execution_result.get("workspace", ""),
    )
    if not isinstance(scores, dict):
        scores = {}
    
    if verbose:
        logger.info("   [VERBOSE] Automated grading scores: %s", scores)

    total = _average_scores(scores)
    return GradeResult(
        task_id=task.task_id,
        score=total,
        max_score=1.0,
        grading_type="automated",
        breakdown=_normalize_score_dict(scores),
        notes="",
    )


def _grade_llm_judge_kimi(
    *,
    task: Task,
    execution_result: Dict[str, Any],
    api_base: str,
    model: str,
    api_key: str,
    timeout_seconds: float = DEFAULT_JUDGE_TIMEOUT_SECONDS,
    verbose: bool = False,
) -> GradeResult:
    """Call Kimi (Moonshot) API directly for grading; returns GradeResult with judge_usage."""
    transcript_summary = _summarize_transcript(execution_result.get("transcript", []))
    if verbose:
        logger.info("   [VERBOSE] Transcript summary for judge (first 1000 chars):\n%s", transcript_summary[:1000])
    rubric = task.llm_judge_rubric or _format_grading_criteria(task)
    prompt = _build_judge_prompt(task, transcript_summary, rubric)

    url = api_base.rstrip("/") + "/chat/completions"
    if not url.startswith("http"):
        url = "https://" + url
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 1,  # this model only allows temperature=1
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    judge_usage: Dict[str, Any] = {
        "model": model,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "execution_time_seconds": 0.0,
        "request_count": 0,
    }
    content_text = ""
    last_error_detail = ""
    request_start = time.time()
    for attempt in range(1, KIMI_JUDGE_MAX_RETRIES + 1):
        judge_usage["request_count"] = attempt
        try:
            with urllib.request.urlopen(req, timeout=int(timeout_seconds)) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            judge_usage["execution_time_seconds"] = round(time.time() - request_start, 3)
            choice = (data.get("choices") or [None])[0]
            if choice and isinstance(choice.get("message"), dict):
                content_text = choice["message"].get("content") or ""
            usage = data.get("usage") or {}
            judge_usage["input_tokens"] = int(usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0))
            judge_usage["output_tokens"] = int(usage.get("completion_tokens", 0) or usage.get("output_tokens", 0))
            judge_usage["total_tokens"] = judge_usage["input_tokens"] + judge_usage["output_tokens"]
            if judge_usage["total_tokens"] > 0:
                cost = (
                    judge_usage["input_tokens"] * (KIMI_JUDGE_PRICE_INPUT_PER_1M / 1e6)
                    + judge_usage["output_tokens"] * (KIMI_JUDGE_PRICE_OUTPUT_PER_1M / 1e6)
                )
                judge_usage["cost_usd"] = round(cost, 6)
            break
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError) as e:
            judge_usage["execution_time_seconds"] = round(time.time() - request_start, 3)
            err_detail = str(e)
            if isinstance(e, urllib.error.HTTPError):
                try:
                    body = e.read().decode("utf-8", errors="replace")
                    if body:
                        err_detail = f"{e.code} {e.reason}: {body[:500]}"
                except Exception:
                    pass
            last_error_detail = err_detail
            if attempt < KIMI_JUDGE_MAX_RETRIES and _is_retryable_kimi_error(e):
                backoff_seconds = attempt
                logger.warning(
                    "Kimi judge API request failed on attempt %s/%s: %s; retrying in %ss",
                    attempt,
                    KIMI_JUDGE_MAX_RETRIES,
                    err_detail,
                    backoff_seconds,
                )
                time.sleep(backoff_seconds)
                continue
            logger.warning("Kimi judge API request failed: %s", err_detail)
            return GradeResult(
                task_id=task.task_id,
                score=0.0,
                max_score=1.0,
                grading_type="llm_judge",
                breakdown={},
                notes=f"Kimi judge API error: {err_detail}",
                judge_usage=judge_usage,
            )

    raw_parsed = _parse_judge_response_text(content_text)
    parsed = _normalize_judge_response(raw_parsed)
    breakdown = parsed.get("scores", {})
    total = parsed.get("total")
    notes = parsed.get("notes", "")
    return GradeResult(
        task_id=task.task_id,
        score=float(total) if total is not None else 0.0,
        max_score=1.0,
        grading_type="llm_judge",
        breakdown=_normalize_score_dict(breakdown),
        notes=str(notes) if notes is not None else "",
        judge_usage=judge_usage,
    )


def _grade_llm_judge(
    *,
    task: Task,
    execution_result: Dict[str, Any],
    judge_model: str,
    judge_agent_prefix: str,
    judge_timeout_seconds: float,
    skill_dir: Path,
    verbose: bool = False,
) -> GradeResult:
    transcript_summary = _summarize_transcript(execution_result.get("transcript", []))
    if verbose:
        logger.info("   [VERBOSE] Transcript summary for judge (first 1000 chars):\n%s", transcript_summary[:1000])
    rubric = task.llm_judge_rubric or _format_grading_criteria(task)
    prompt = _build_judge_prompt(task, transcript_summary, rubric)

    agent_id = _ensure_judge_agent(judge_agent_prefix, judge_model, skill_dir)
    judge_workspace = Path(f"/tmp/pinchbench/judge/{task.task_id}")
    judge_result = run_openclaw_prompt(
        agent_id=agent_id,
        prompt=prompt,
        workspace=judge_workspace,
        timeout_seconds=judge_timeout_seconds,
    )

    raw_parsed = _parse_judge_response(judge_result.get("transcript", []))
    if verbose:
        logger.info("   [VERBOSE] Judge raw response parsed: %s", raw_parsed)
    
    # Normalize the response to handle various formats (criteria_scores, score, justification, etc.)
    parsed = _normalize_judge_response(raw_parsed)
    if verbose:
        logger.info("   [VERBOSE] Normalized judge response: %s", parsed)
    
    breakdown = parsed.get("scores", {})
    total = parsed.get("total")
    notes = parsed.get("notes", "")
    return GradeResult(
        task_id=task.task_id,
        score=float(total) if total is not None else 0.0,
        max_score=1.0,
        grading_type="llm_judge",
        breakdown=_normalize_score_dict(breakdown),
        notes=str(notes) if notes is not None else "",
    )


def _combine_grades(task: Task, auto_result: GradeResult, llm_result: GradeResult) -> GradeResult:
    weights = task.grading_weights or {"automated": 0.5, "llm_judge": 0.5}
    auto_weight = float(weights.get("automated", 0.5))
    llm_weight = float(weights.get("llm_judge", 0.5))
    total_weight = auto_weight + llm_weight
    if total_weight <= 0:
        auto_weight = llm_weight = 0.5
        total_weight = 1.0
    combined_score = (
        auto_result.score * auto_weight + llm_result.score * llm_weight
    ) / total_weight
    breakdown = {
        **{f"automated.{k}": v for k, v in auto_result.breakdown.items()},
        **{f"llm_judge.{k}": v for k, v in llm_result.breakdown.items()},
    }
    notes = " | ".join(filter(None, [auto_result.notes, llm_result.notes]))
    return GradeResult(
        task_id=task.task_id,
        score=combined_score,
        max_score=1.0,
        grading_type="hybrid",
        breakdown=breakdown,
        notes=notes,
        judge_usage=llm_result.judge_usage,
    )


def _extract_grading_code(task: Task) -> str:
    if not task.automated_checks:
        return ""
    match = re.search(r"```python\s*(.*?)\s*```", task.automated_checks, re.DOTALL)
    if not match:
        return ""
    return match.group(1)


def _average_scores(scores: Dict[str, Any]) -> float:
    values = [float(v) for v in scores.values() if isinstance(v, (int, float))]
    if not values:
        return 0.0
    return sum(values) / len(values)


def _normalize_score_dict(scores: Dict[str, Any]) -> Dict[str, float]:
    normalized: Dict[str, float] = {}
    for key, value in scores.items():
        try:
            normalized[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return normalized


def _format_grading_criteria(task: Task) -> str:
    if not task.grading_criteria:
        return ""
    return "\n".join(f"- {criterion}" for criterion in task.grading_criteria)


def _summarize_transcript(transcript: List[Dict[str, Any]]) -> str:
    summary_parts: List[str] = []
    for event in transcript:
        if event.get("type") != "message":
            continue
        msg = event.get("message", {})
        role = msg.get("role")
        if role == "assistant":
            for item in msg.get("content", []):
                if item.get("type") == "toolCall":
                    summary_parts.append(
                        f"Tool: {item.get('name')}({json.dumps(item.get('arguments', {}))})"
                    )
        elif role == "toolResult":
            content = msg.get("content", [])
            if content:
                result_preview = str(content[0])[:200]
                summary_parts.append(f"Result: {result_preview}")
        elif role == "user":
            content = msg.get("content", [])
            if content:
                summary_parts.append(f"User: {content[0]}")
    return "\n".join(summary_parts)


def _build_judge_prompt(task: Task, transcript_summary: str, rubric: str) -> str:
    return (
        "You are a grading function. Your ONLY job is to output a single JSON object.\n\n"
        "CRITICAL RULES:\n"
        "- Do NOT use any tools (no Read, Write, exec, or any other tool calls)\n"
        "- Do NOT create files or run commands\n"
        "- Do NOT write any prose, explanation, or commentary outside the JSON\n"
        "- Respond with ONLY a JSON object — nothing else\n\n"
        "Be a strict evaluator. Reserve 1.0 for genuinely excellent performance. "
        "An average acceptable completion should score around 0.6-0.7. "
        "Deduct points for unnecessary steps, verbose output, and inefficient tool usage.\n\n"
        "## Task\n"
        f"{task.prompt}\n\n"
        "## Expected Behavior\n"
        f"{task.expected_behavior}\n\n"
        "## Agent Transcript (summarized)\n"
        f"{transcript_summary}\n\n"
        "## Grading Rubric\n"
        f"{rubric}\n\n"
        "Score each criterion from 0.0 to 1.0.\n\n"
        "Respond with ONLY this JSON structure (no markdown, no code fences, no extra text):\n"
        '{"scores": {"criterion_name": 0.0}, "total": 0.0, "notes": "brief justification"}'
    )


def _ensure_judge_agent(judge_agent_prefix: str, judge_model: str, skill_dir: Path) -> str:
    model_slug = slugify_model(judge_model)
    agent_id = f"{judge_agent_prefix}-{model_slug}"
    workspace = Path("/tmp/pinchbench/judge/workspace")
    ensure_agent_exists(agent_id, judge_model, workspace)
    return agent_id


def _parse_judge_response(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    content_chunks: List[str] = []
    for event in transcript:
        if event.get("type") != "message":
            continue
        msg = event.get("message", {})
        if msg.get("role") != "assistant":
            continue
        for item in msg.get("content", []):
            if item.get("type") == "text":
                content_chunks.append(item.get("text", ""))
    raw_text = "\n".join(content_chunks).strip()
    return _parse_judge_response_text(raw_text)


def _parse_judge_response_text(raw_text: str) -> Dict[str, Any]:
    """Parse judge JSON from raw response text (from transcript or direct API content)."""
    if not raw_text or not raw_text.strip():
        return {}

    raw_text = raw_text.strip()
    # First, try to extract JSON from code blocks (```json ... ```)
    code_block_match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL)
    if code_block_match:
        try:
            parsed = json.loads(code_block_match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Find all potential JSON objects by looking for balanced braces
    # We'll extract chunks that start with { and try to parse them
    json_candidates: List[str] = []
    brace_depth = 0
    current_json = []
    for char in raw_text:
        if char == "{":
            if brace_depth == 0:
                current_json = []
            brace_depth += 1

        if brace_depth > 0:
            current_json.append(char)

        if char == "}":
            brace_depth -= 1
            if brace_depth == 0 and current_json:
                json_candidates.append("".join(current_json))

    # Try parsing from the last JSON object backwards (most recent response)
    for candidate in reversed(json_candidates):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "scores" in parsed:
                # Prefer JSON that has the expected structure
                return parsed
        except json.JSONDecodeError:
            continue

    # Try any valid JSON dict
    for candidate in reversed(json_candidates):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # Fallback: try to extract numeric scores from prose responses.
    # Models sometimes return "Total: 0.72" or "Overall score: 0.65" instead of JSON.
    score_pattern = re.search(
        r"(?:total|overall|final)\s*(?:score)?[:\s]*(0\.\d+|1\.0+)",
        raw_text,
        re.IGNORECASE,
    )
    if score_pattern:
        try:
            total = float(score_pattern.group(1))
            if 0.0 <= total <= 1.0:
                logger.warning(
                    "Fell back to regex score extraction from prose (total=%.2f)", total
                )
                return {"scores": {}, "total": total, "notes": "Score extracted from prose (JSON parse failed)"}
        except ValueError:
            pass

    logger.warning("Failed to parse judge JSON response")
    return {}


def _normalize_judge_response(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize judge response to expected format with 'scores', 'total', and 'notes'.
    
    Handles various response formats:
    - {"scores": {...}, "total": 0.9, "notes": "..."}  (expected)
    - {"criteria_scores": {...}, ...}  (Claude sometimes uses this)
    - {"score": 0.9, "justification": "..."}  (simplified format)
    """
    result: Dict[str, Any] = {"scores": {}, "total": None, "notes": ""}
    
    # Extract scores from various keys
    if "scores" in parsed:
        scores_data = parsed["scores"]
        if isinstance(scores_data, dict):
            # Handle nested structure: {"criterion": {"score": 0.9, "weight": 0.3}}
            for key, value in scores_data.items():
                if isinstance(value, dict) and "score" in value:
                    result["scores"][key] = float(value["score"]) if isinstance(value["score"], (int, float, str)) else value["score"]
                elif isinstance(value, (int, float)):
                    result["scores"][key] = value
    elif "criteria_scores" in parsed:
        # Handle Claude's alternate format
        criteria = parsed["criteria_scores"]
        if isinstance(criteria, dict):
            for key, value in criteria.items():
                if isinstance(value, dict) and "score" in value:
                    result["scores"][key] = value["score"]
                elif isinstance(value, (int, float)):
                    result["scores"][key] = value
    
    # Extract total score
    if "total" in parsed and parsed["total"] is not None:
        result["total"] = float(parsed["total"]) if isinstance(parsed["total"], (int, float)) else None
    elif "score" in parsed and isinstance(parsed["score"], (int, float)):
        result["total"] = float(parsed["score"])
    elif result["scores"]:
        # Calculate average if we have individual scores but no total
        values = [v for v in result["scores"].values() if isinstance(v, (int, float))]
        if values:
            result["total"] = sum(values) / len(values)
    
    # Extract notes/justification
    if "notes" in parsed:
        result["notes"] = str(parsed["notes"])
    elif "justification" in parsed:
        result["notes"] = str(parsed["justification"])
    elif "reasoning" in parsed:
        result["notes"] = str(parsed["reasoning"])
    
    return result
