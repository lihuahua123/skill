#!/usr/bin/env python3
"""
Early-stop policy helpers for SkillsBench.

This module is intentionally small and rule-based:

1. Intra-attempt
   - route a task into one of three policy families
   - retrieve similar historical cases instead of training a predictor

2. Inter-attempt
   - compare verifier-visible signals across attempts
   - stop only when verifier evidence does not narrow

The caller is expected to provide task metadata / attempts in the same broad
shape as the aggregated SkillsBench JSON already produced in this repo.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TaskPolicy = str
TASK_POLICY_AGGRESSIVE = "aggressive-stop-safe"
TASK_POLICY_CONSERVATIVE = "conservative-stop"
TASK_POLICY_DRIFT_ONLY = "drift-only-stop"


TASK_FAMILY_HINTS: dict[TaskPolicy, dict[str, tuple[str, ...]]] = {
    TASK_POLICY_AGGRESSIVE: {
        "task_ids": (
            "court-form-filling",
            "offer-letter-generator",
            "dialogue-parser",
            "setup-fuzzing-py",
            "organize-messy-files",
        ),
        "keywords": (
            "form",
            "pdf",
            "fill",
            "field",
            "schema",
            "output file",
            "directory structure",
            "contract",
            "rename",
            "organize files",
        ),
    },
    TASK_POLICY_CONSERVATIVE: {
        "task_ids": (
            "sec-financial-report",
            "adaptive-cruise-control",
            "pedestrian-traffic-counting",
            "pg-essay-to-audiobook",
            "mars-clouds-clustering",
            "shock-analysis-supply",
            "lab-unit-harmonization",
            "suricata-custom-exfil",
        ),
        "keywords": (
            "analysis",
            "report",
            "financial",
            "simulation",
            "cluster",
            "clustering",
            "audio",
            "video",
            "counting",
            "time series",
            "harmonization",
            "suricata",
            "rule",
            "control",
            "fuzzing",
            "data",
            "csv",
            "pandas",
        ),
    },
    TASK_POLICY_DRIFT_ONLY: {
        "task_ids": (
            "fix-build-google-auto",
            "fix-build-agentops",
            "lean4-proof",
            "scheduling-email-assistant",
        ),
        "keywords": (
            "build",
            "repo",
            "compile",
            "dependency",
            "env",
            "environment variable",
            "proof",
            "lean",
            "assistant",
            "schedule",
            "email",
            "debug",
        ),
    },
}


HEAVY_KEYWORDS = {
    "analysis",
    "simulation",
    "cluster",
    "audio",
    "video",
    "csv",
    "data",
    "financial",
    "report",
    "counting",
    "control",
}

REPO_DEBUG_KEYWORDS = {
    "build",
    "repo",
    "compile",
    "dependency",
    "importerror",
    "environment variable",
    "lean",
    "toolchain",
}

STRUCTURED_OUTPUT_KEYWORDS = {
    "form",
    "pdf",
    "field",
    "schema",
    "json",
    "yaml",
    "output file",
    "directory",
}


@dataclass
class TaskStaticInfo:
    task_id: str
    instruction: str = ""
    verifier_notes: str = ""
    expected_outputs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass
class AttemptVerifierSummary:
    reward: float = 0.0
    unresolved_criteria_count: int | None = None
    feedback_items: tuple[str, ...] = ()
    notes: str = ""
    passed: bool = False


@dataclass
class SimilarCase:
    task_id: str
    policy: TaskPolicy
    score: int
    reasons: list[str] = field(default_factory=list)
    attempt_count: int = 0
    success: bool = False
    first_success_attempt: int | None = None


@dataclass
class InterAttemptDecision:
    should_stop: bool
    reason: str
    evidence: list[str] = field(default_factory=list)


EARLY_STOP_STRATEGY_HEURISTIC = "heuristic"
EARLY_STOP_STRATEGY_PAPER_DYNAMIC_TURN = "paper-dynamic-turn"


@dataclass(frozen=True)
class PaperDynamicTurnConfig:
    initial_turn_limit: int
    extension_turn_limit: int

    @property
    def total_turn_limit(self) -> int:
        return self.initial_turn_limit + self.extension_turn_limit


@dataclass(frozen=True)
class PaperDynamicTurnDecision:
    should_stop: bool
    phase: str
    turns_used: int
    turns_remaining_in_phase: int
    total_turn_limit: int
    reason: str


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    return re.sub(r"\s+", " ", text)


def _as_tuple_str(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if item is not None)
    if value is None:
        return ()
    return (str(value),)


def _extract_keywords(text: str) -> set[str]:
    normalized = _normalize_text(text)
    words = set(re.findall(r"[a-z0-9][a-z0-9_-]{2,}", normalized))
    return words


def build_task_static_info(task: dict[str, Any]) -> TaskStaticInfo:
    frontmatter = task.get("frontmatter") or {}
    instruction = (
        frontmatter.get("instruction")
        or frontmatter.get("prompt")
        or task.get("instruction")
        or task.get("description")
        or ""
    )
    verifier_notes = ""
    attempts = task.get("attempts") or []
    if attempts:
        last_verifier = (attempts[-1].get("verifier") or {})
        verifier_notes = str(last_verifier.get("notes") or "")
    expected_outputs = _as_tuple_str(
        frontmatter.get("expected_outputs") or frontmatter.get("outputs") or task.get("expected_outputs")
    )
    tags = _as_tuple_str(frontmatter.get("tags") or task.get("tags"))
    return TaskStaticInfo(
        task_id=str(task.get("task_id") or ""),
        instruction=str(instruction or ""),
        verifier_notes=verifier_notes,
        expected_outputs=expected_outputs,
        tags=tags,
    )


def build_attempt_verifier_summary(attempt: dict[str, Any]) -> AttemptVerifierSummary:
    verifier = attempt.get("verifier") or {}
    feedback = verifier.get("feedback") or verifier.get("feedback_items") or []
    reward = verifier.get("reward")
    if reward is None:
        grading = attempt.get("grading") or {}
        reward = grading.get("score", 0.0)
    return AttemptVerifierSummary(
        reward=float(reward or 0.0),
        unresolved_criteria_count=attempt.get("unresolved_criteria_count"),
        feedback_items=tuple(str(item) for item in feedback if item),
        notes=str(verifier.get("notes") or ""),
        passed=bool((attempt.get("grading") or {}).get("passed") or float(reward or 0.0) >= 1.0),
    )


def route_task_family(task_info: TaskStaticInfo) -> TaskPolicy:
    task_id = _normalize_text(task_info.task_id)
    bag = " ".join(
        (
            task_info.task_id,
            task_info.instruction,
            task_info.verifier_notes,
            " ".join(task_info.expected_outputs),
            " ".join(task_info.tags),
        )
    )
    normalized_bag = _normalize_text(bag)

    for policy, hints in TASK_FAMILY_HINTS.items():
        if task_id in {_normalize_text(item) for item in hints["task_ids"]}:
            return policy
        if any(keyword in normalized_bag for keyword in hints["keywords"]):
            return policy

    words = _extract_keywords(normalized_bag)
    if words & REPO_DEBUG_KEYWORDS:
        return TASK_POLICY_DRIFT_ONLY
    if words & HEAVY_KEYWORDS:
        return TASK_POLICY_CONSERVATIVE
    if words & STRUCTURED_OUTPUT_KEYWORDS:
        return TASK_POLICY_AGGRESSIVE
    return TASK_POLICY_CONSERVATIVE


def _task_feature_flags(task_info: TaskStaticInfo) -> dict[str, bool]:
    bag = _normalize_text(
        " ".join(
            (
                task_info.task_id,
                task_info.instruction,
                task_info.verifier_notes,
                " ".join(task_info.expected_outputs),
                " ".join(task_info.tags),
            )
        )
    )
    words = _extract_keywords(bag)
    return {
        "repo_debug": bool(words & REPO_DEBUG_KEYWORDS),
        "structured_output": bool(words & STRUCTURED_OUTPUT_KEYWORDS),
        "data_heavy": bool(words & HEAVY_KEYWORDS),
        "simulation_heavy": any(token in bag for token in ("simulation", "control", "sensor", "trajectory")),
        "media_heavy": any(token in bag for token in ("audio", "video", "subtitle", "speech")),
    }


def retrieve_similar_cases(
    task_info: TaskStaticInfo,
    historical_tasks: list[dict[str, Any]],
    *,
    top_k: int = 5,
) -> list[SimilarCase]:
    query_policy = route_task_family(task_info)
    query_flags = _task_feature_flags(task_info)
    query_words = _extract_keywords(
        " ".join((task_info.task_id, task_info.instruction, task_info.verifier_notes, " ".join(task_info.tags)))
    )

    cases: list[SimilarCase] = []
    for task in historical_tasks:
        candidate_info = build_task_static_info(task)
        candidate_policy = route_task_family(candidate_info)
        candidate_flags = _task_feature_flags(candidate_info)
        candidate_words = _extract_keywords(
            " ".join(
                (
                    candidate_info.task_id,
                    candidate_info.instruction,
                    candidate_info.verifier_notes,
                    " ".join(candidate_info.tags),
                )
            )
        )

        score = 0
        reasons: list[str] = []

        if candidate_policy == query_policy:
            score += 4
            reasons.append(f"same policy family: {query_policy}")

        shared_flags = [name for name, enabled in query_flags.items() if enabled and candidate_flags.get(name)]
        if shared_flags:
            score += len(shared_flags) * 2
            reasons.append(f"shared task traits: {', '.join(sorted(shared_flags))}")

        shared_words = sorted(query_words & candidate_words)
        if shared_words:
            score += min(4, len(shared_words))
            reasons.append(f"shared keywords: {', '.join(shared_words[:4])}")

        if task_info.task_id and candidate_info.task_id == task_info.task_id:
            score += 6
            reasons.append("same task id")

        if score <= 0:
            continue

        cases.append(
            SimilarCase(
                task_id=candidate_info.task_id,
                policy=candidate_policy,
                score=score,
                reasons=reasons,
                attempt_count=int(task.get("attempt_count") or len(task.get("attempts") or [])),
                success=bool(task.get("status") == "success" or task.get("success_within_budget")),
                first_success_attempt=task.get("first_success_attempt"),
            )
        )

    cases.sort(key=lambda item: (-item.score, item.task_id))
    return cases[: max(1, top_k)]


def recommend_intra_attempt_mode(
    task_info: TaskStaticInfo,
    historical_tasks: list[dict[str, Any]],
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    routed_policy = route_task_family(task_info)
    neighbors = retrieve_similar_cases(task_info, historical_tasks, top_k=top_k)

    if not neighbors:
        return {
            "policy": routed_policy,
            "confidence": "route-only",
            "neighbor_cases": [],
            "guidance": (
                "No close historical case found; use the routed policy only and keep "
                "intra-attempt stopping conservative."
            ),
        }

    success_neighbors = sum(1 for case in neighbors if case.success)
    long_retry_neighbors = sum(1 for case in neighbors if case.attempt_count >= 3)
    conservative_bias = routed_policy == TASK_POLICY_CONSERVATIVE or long_retry_neighbors >= max(2, top_k // 2)

    guidance = "Trust drift / obvious prerequisite failures first."
    if routed_policy == TASK_POLICY_AGGRESSIVE and success_neighbors >= max(1, top_k // 2):
        guidance = "Similar cases look structurally stable; aggressive intra-attempt stop is relatively safe."
    elif conservative_bias:
        guidance = (
            "Similar cases are heavy or multi-attempt; be conservative and only trust "
            "strong drift / no-progress evidence."
        )
    elif routed_policy == TASK_POLICY_DRIFT_ONLY:
        guidance = "Only trust clear task drift or prerequisite-mismatch signals."

    return {
        "policy": routed_policy,
        "confidence": "neighbors-informed",
        "neighbor_cases": [
            {
                "task_id": case.task_id,
                "policy": case.policy,
                "score": case.score,
                "success": case.success,
                "attempt_count": case.attempt_count,
                "reasons": case.reasons,
            }
            for case in neighbors
        ],
        "guidance": guidance,
    }


def _feedback_signatures(summary: AttemptVerifierSummary) -> set[str]:
    signatures: set[str] = set()
    for item in summary.feedback_items:
        normalized = _normalize_text(item)
        if normalized:
            signatures.add(normalized)
    notes = _normalize_text(summary.notes)
    for pattern in (
        r"failed tests?:\s*(.+)",
        r"error collecting\s+(.+)",
        r"assertionerror:\s*(.+)",
        r"file or directory not found:\s*(.+)",
    ):
        for match in re.findall(pattern, notes):
            value = _normalize_text(match)
            if value:
                signatures.add(value)
    return signatures


def _note_specificity(summary: AttemptVerifierSummary) -> int:
    score = 0
    note = _normalize_text(summary.notes)
    if summary.feedback_items:
        score += 2
    if "::" in note or "failed tests:" in note:
        score += 2
    if "assertionerror" in note or "expected" in note or "got:" in note:
        score += 2
    if "error collecting" in note or "command not found" in note or "environment variable" in note:
        score += 1
    return score


def compare_verifier_progress(
    previous_attempt: dict[str, Any],
    current_attempt: dict[str, Any],
) -> dict[str, Any]:
    prev = build_attempt_verifier_summary(previous_attempt)
    curr = build_attempt_verifier_summary(current_attempt)
    prev_signatures = _feedback_signatures(prev)
    curr_signatures = _feedback_signatures(curr)

    evidence: list[str] = []
    narrowed = False

    if curr.passed:
        evidence.append("current attempt passed verifier")
        narrowed = True

    if curr.reward > prev.reward:
        evidence.append(f"reward improved: {prev.reward:.3f} -> {curr.reward:.3f}")
        narrowed = True

    prev_unresolved = prev.unresolved_criteria_count
    curr_unresolved = curr.unresolved_criteria_count
    if prev_unresolved is not None and curr_unresolved is not None:
        if curr_unresolved < prev_unresolved:
            evidence.append(f"unresolved criteria decreased: {prev_unresolved} -> {curr_unresolved}")
            narrowed = True
        elif curr_unresolved > prev_unresolved:
            evidence.append(f"unresolved criteria increased: {prev_unresolved} -> {curr_unresolved}")

    if prev_signatures and curr_signatures:
        removed = prev_signatures - curr_signatures
        added = curr_signatures - prev_signatures
        if removed and not added:
            evidence.append("verifier failure signatures strictly narrowed")
            narrowed = True
        elif removed:
            evidence.append("some prior verifier failures disappeared")
            narrowed = True

    prev_specificity = _note_specificity(prev)
    curr_specificity = _note_specificity(curr)
    if curr_specificity > prev_specificity:
        evidence.append(f"verifier notes became more specific: {prev_specificity} -> {curr_specificity}")
        narrowed = True

    stagnated = not narrowed
    if not evidence:
        evidence.append("no verifier-visible improvement detected")

    return {
        "narrowed": narrowed,
        "stagnated": stagnated,
        "previous_signatures": sorted(prev_signatures),
        "current_signatures": sorted(curr_signatures),
        "evidence": evidence,
    }


def decide_inter_attempt_stop(
    previous_attempt: dict[str, Any],
    current_attempt: dict[str, Any],
) -> InterAttemptDecision:
    progress = compare_verifier_progress(previous_attempt, current_attempt)
    if progress["narrowed"]:
        return InterAttemptDecision(
            should_stop=False,
            reason="continue: verifier evidence narrowed",
            evidence=list(progress["evidence"]),
        )
    return InterAttemptDecision(
        should_stop=True,
        reason="stop: verifier evidence did not narrow across attempts",
        evidence=list(progress["evidence"]),
    )


def load_historical_tasks(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        tasks = payload.get("tasks")
        if isinstance(tasks, list):
            return [task for task in tasks if isinstance(task, dict)]
    if isinstance(payload, list):
        return [task for task in payload if isinstance(task, dict)]
    return []


def validate_paper_dynamic_turn_config(
    initial_turn_limit: int,
    extension_turn_limit: int,
) -> PaperDynamicTurnConfig:
    if int(initial_turn_limit) <= 0:
        raise ValueError("initial_turn_limit must be a positive integer")
    if int(extension_turn_limit) <= 0:
        raise ValueError("extension_turn_limit must be a positive integer")
    return PaperDynamicTurnConfig(
        initial_turn_limit=int(initial_turn_limit),
        extension_turn_limit=int(extension_turn_limit),
    )


def decide_paper_dynamic_turn(
    turns_used: int,
    *,
    patch_detected: bool,
    config: PaperDynamicTurnConfig,
) -> PaperDynamicTurnDecision:
    used = max(0, int(turns_used))
    total_limit = config.total_turn_limit

    if patch_detected:
        return PaperDynamicTurnDecision(
            should_stop=False,
            phase="patch-detected",
            turns_used=used,
            turns_remaining_in_phase=max(total_limit - used, 0),
            total_turn_limit=total_limit,
            reason="workspace already has a non-empty patch; do not early-stop",
        )

    if used < config.initial_turn_limit:
        return PaperDynamicTurnDecision(
            should_stop=False,
            phase="initial-budget",
            turns_used=used,
            turns_remaining_in_phase=config.initial_turn_limit - used,
            total_turn_limit=total_limit,
            reason=(
                "still within initial dynamic-turn budget "
                f"({used}/{config.initial_turn_limit} turns used)"
            ),
        )

    if used < total_limit:
        return PaperDynamicTurnDecision(
            should_stop=False,
            phase="extension-budget",
            turns_used=used,
            turns_remaining_in_phase=total_limit - used,
            total_turn_limit=total_limit,
            reason=(
                "initial budget exhausted without patch; using one-time extension "
                f"({used}/{total_limit} total turns used)"
            ),
        )

    return PaperDynamicTurnDecision(
        should_stop=True,
        phase="stop",
        turns_used=used,
        turns_remaining_in_phase=0,
        total_turn_limit=total_limit,
        reason=(
            "stop: no non-empty patch after initial budget and one-time extension "
            f"({used}/{total_limit} total turns used)"
        ),
    )


__all__ = [
    "EARLY_STOP_STRATEGY_HEURISTIC",
    "EARLY_STOP_STRATEGY_PAPER_DYNAMIC_TURN",
    "PaperDynamicTurnConfig",
    "PaperDynamicTurnDecision",
    "TASK_POLICY_AGGRESSIVE",
    "TASK_POLICY_CONSERVATIVE",
    "TASK_POLICY_DRIFT_ONLY",
    "AttemptVerifierSummary",
    "InterAttemptDecision",
    "SimilarCase",
    "TaskStaticInfo",
    "build_attempt_verifier_summary",
    "build_task_static_info",
    "compare_verifier_progress",
    "decide_paper_dynamic_turn",
    "decide_inter_attempt_stop",
    "load_historical_tasks",
    "recommend_intra_attempt_mode",
    "retrieve_similar_cases",
    "route_task_family",
    "validate_paper_dynamic_turn_config",
]
