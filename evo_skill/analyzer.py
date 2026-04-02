from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .types import ExecutionAnalysis, EvolutionSuggestion, EvolutionType


def load_result_records(results_dir: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path in sorted(results_dir.glob("*.json")):
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        records.extend(_normalize_payload(payload, path))
    return records


def _normalize_payload(payload: Any, path: Path) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("series")
        if isinstance(items, list):
            normalized = [item for item in items if isinstance(item, dict)]
        else:
            normalized = [payload]
    elif isinstance(payload, list):
        normalized = [item for item in payload if isinstance(item, dict)]
    else:
        return []
    for item in normalized:
        item["_source_file"] = str(path)
    return normalized


def load_task_skill_usage(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: Dict[str, Dict[str, Any]] = {}
    for item in payload.get("tasks", []):
        benchmark = str(item.get("benchmark", ""))
        task_id = str(item.get("task_id", ""))
        if benchmark and task_id:
            result[f"{benchmark}:{task_id}"] = item
    return result


def analyze_results(
    records: Iterable[Dict[str, Any]],
    *,
    task_skill_usage: Optional[Dict[str, Dict[str, Any]]] = None,
    benchmark_filter: Optional[str] = None,
) -> List[ExecutionAnalysis]:
    analyses: List[ExecutionAnalysis] = []
    usage_index = task_skill_usage or {}
    for result in records:
        benchmark = str(result.get("benchmark") or _infer_benchmark(result))
        if benchmark_filter and benchmark != benchmark_filter:
            continue
        source_file = str(result.get("_source_file", ""))
        for task in result.get("tasks", []):
            usage = usage_index.get(f"{benchmark}:{task.get('task_id', 'unknown-task')}")
            analysis = _analyze_task(
                result,
                task,
                benchmark=benchmark,
                source_file=source_file,
                task_skill_usage=usage,
            )
            if analysis.evolution_suggestions:
                analyses.append(analysis)
    return analyses


def _infer_benchmark(result: Dict[str, Any]) -> str:
    source = str(result.get("_source_file", ""))
    if "skillsbench" in source:
        return "skillsbench"
    return "pinchbench"


def _analyze_task(
    result: Dict[str, Any],
    task: Dict[str, Any],
    *,
    benchmark: str,
    source_file: str,
    task_skill_usage: Optional[Dict[str, Any]] = None,
) -> ExecutionAnalysis:
    task_id = str(task.get("task_id", "unknown-task"))
    attempts = task.get("attempts", []) or []
    final_attempt = attempts[-1] if attempts else {}
    completed = bool(task.get("success_within_budget"))
    attempt_count = int(task.get("attempt_count") or len(attempts) or 0)
    first_success_attempt = task.get("first_success_attempt")
    unresolved = _last_numeric(task.get("unresolved_criteria_count_by_attempt", []))
    transcript_text = "\n".join(_iter_transcripts(attempts))
    repeated_errors = _find_repeated_failures(transcript_text)

    note_parts = [
        f"benchmark={benchmark}",
        f"attempt_count={attempt_count}",
        f"first_success_attempt={first_success_attempt}",
    ]
    if unresolved is not None:
        note_parts.append(f"last_unresolved_criteria={unresolved}")
    if repeated_errors:
        note_parts.append(f"repeated_failures={', '.join(repeated_errors[:3])}")
    parent_candidates = _parent_skill_candidates(benchmark, task_skill_usage)
    if parent_candidates:
        note_parts.append(
            "parent_candidates=" + ",".join(parent_candidates[:4])
        )

    suggestions = _build_suggestions(
        benchmark=benchmark,
        task_id=task_id,
        completed=completed,
        attempt_count=attempt_count,
        first_success_attempt=first_success_attempt,
        unresolved=unresolved,
        transcript_text=transcript_text,
        final_attempt=final_attempt,
        parent_candidates=parent_candidates,
    )

    return ExecutionAnalysis(
        analysis_id=f"{benchmark}::{task_id}::{_slugify(Path(source_file).stem)}",
        benchmark=benchmark,
        source_file=source_file,
        task_id=task_id,
        task_completed=completed,
        execution_note="; ".join(note_parts),
        evolution_suggestions=suggestions,
        metrics={
            "attempt_count": attempt_count,
            "first_success_attempt": first_success_attempt,
            "last_unresolved_criteria_count": unresolved,
            "parent_skill_candidates": parent_candidates,
            "total_tokens": (
                final_attempt.get("execution", {})
                .get("cumulative_usage", {})
                .get("total_tokens")
            ),
        },
    )


def _build_suggestions(
    *,
    benchmark: str,
    task_id: str,
    completed: bool,
    attempt_count: int,
    first_success_attempt: Any,
    unresolved: Any,
    transcript_text: str,
    final_attempt: Dict[str, Any],
    parent_candidates: List[str],
) -> List[EvolutionSuggestion]:
    suggestions: List[EvolutionSuggestion] = []
    base_parent_ids = parent_candidates or [f"{benchmark}-retry-core"]

    if completed and attempt_count >= 2 and first_success_attempt not in (None, 1):
        suggestions.append(
            EvolutionSuggestion(
                evolution_type=EvolutionType.DERIVED,
                target_skill_ids=base_parent_ids,
                category="workflow",
                direction=(
                    f"Capture the successful repair loop for {task_id}. "
                    "Emphasize narrowing from full rework to verifier-visible repair."
                ),
                rationale=(
                    "Task succeeded only after retries, which matches the OpenSpace "
                    "derived-skill pattern: preserve the parent workflow and add a "
                    "more specific retry strategy."
                ),
            )
        )

    if (not completed) and attempt_count >= 2:
        suggestions.append(
            EvolutionSuggestion(
                evolution_type=EvolutionType.FIX,
                target_skill_ids=base_parent_ids,
                category="workflow",
                direction=(
                    f"Fix retry handling for {task_id}. Add earlier stop conditions, "
                    "output-contract checks, and failure-class detection."
                ),
                rationale=(
                    "Task kept retrying without reaching success; this maps to the "
                    "OpenSpace fix pattern for an existing skill that is applied but "
                    "not reliably effective."
                ),
            )
        )

    if _looks_like_new_pattern(task_id, transcript_text, unresolved):
        suggestions.append(
            EvolutionSuggestion(
                evolution_type=EvolutionType.CAPTURED,
                target_skill_ids=[],
                category="workflow",
                direction=(
                    f"Capture a reusable task-family playbook from {task_id}, "
                    "including verifier-first repair and artifact validation."
                ),
                rationale=(
                    "The task shows a reusable workflow pattern that should exist as "
                    "a standalone skill rather than only as a retry tweak."
                ),
            )
        )

    return suggestions


def _iter_transcripts(attempts: List[Dict[str, Any]]) -> Iterable[str]:
    for attempt in attempts:
        transcript = attempt.get("execution", {}).get("transcript")
        if isinstance(transcript, str) and transcript.strip():
            yield transcript


def _find_repeated_failures(transcript_text: str) -> List[str]:
    patterns = {
        "missing_output": r"missing output|no such file|not found",
        "timeout": r"timed out|timeout",
        "validator_failure": r"validator|verification failed|assert",
        "environment": r"module not found|command not found|dependency",
    }
    found: List[str] = []
    lowered = transcript_text.lower()
    for name, pattern in patterns.items():
        if re.search(pattern, lowered):
            found.append(name)
    return found


def _looks_like_new_pattern(task_id: str, transcript_text: str, unresolved: Any) -> bool:
    families = (
        "xlsx",
        "pdf",
        "planning",
        "scala",
        "fuzz",
        "detection",
        "form",
        "report",
    )
    if any(token in task_id for token in families):
        return True
    if unresolved not in (None, 0) and "validator" in transcript_text.lower():
        return True
    return False


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


def _last_numeric(values: List[Any]) -> Any:
    numeric = [value for value in values if isinstance(value, (int, float))]
    return numeric[-1] if numeric else None


def _parent_skill_candidates(benchmark: str, task_skill_usage: Optional[Dict[str, Any]]) -> List[str]:
    if not task_skill_usage:
        return []
    ranked = sorted(
        task_skill_usage.get("skills", []),
        key=lambda item: (
            0 if "skill_loaded" in item.get("evidence_types", []) else 1,
            0 if "skill_script_invoked" in item.get("evidence_types", []) else 1,
            item.get("skill_name", ""),
        ),
    )
    candidates: List[str] = []
    for skill in ranked:
        name = skill.get("skill_name")
        if not name:
            continue
        normalized = _slugify(str(name))
        if normalized not in candidates:
            candidates.append(normalized)
    return candidates[:3]
