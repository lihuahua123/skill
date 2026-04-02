#!/usr/bin/env python3
"""Route benchmark-like requests into direct reuse, macro reuse, or full-model execution."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "catalog.json"


@dataclass
class RouteDecision:
    mode: str
    family_id: str | None
    template_name: str | None
    total_score: int
    feature_breakdown: dict[str, int]
    matched_tasks: list[str]
    reasons: list[str]
    fallback: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "family_id": self.family_id,
            "template_name": self.template_name,
            "total_score": self.total_score,
            "feature_breakdown": self.feature_breakdown,
            "matched_tasks": self.matched_tasks,
            "reasons": self.reasons,
            "fallback": self.fallback,
        }


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text())


def normalize(text: str) -> str:
    return " ".join(text.lower().replace("_", " ").replace("-", " ").split())


def contains_term(normalized_text: str, term: str) -> bool:
    normalized_term = normalize(term)
    if not normalized_term:
        return False
    if " " in normalized_term:
        return normalized_term in normalized_text
    return re.search(rf"\b{re.escape(normalized_term)}\b", normalized_text) is not None


def infer_features(text: str) -> tuple[dict[str, int], list[str]]:
    normalized = normalize(text)
    features = {
        "stable_output_format": 0,
        "stable_tool_sequence": 0,
        "parameter_substitution": 0,
        "local_validator_repair": 0,
        "open_ended_search": 0,
        "repo_specific_debugging": 0,
        "long_horizon_reasoning": 0,
    }
    reasons: list[str] = []

    structured_output_terms = [
        "save to",
        "write to",
        "output file",
        "json",
        "csv",
        "xlsx",
        "pdf",
        "ics",
        "markdown",
        "one answer per line",
        "fill the form",
    ]
    stable_tool_terms = [
        "read the file",
        "extract",
        "parse",
        "write",
        "save",
        "summarize",
        "fill",
        "replace",
        "classify",
        "triage",
    ]
    substitution_terms = [
        "based on",
        "use the case description",
        "provided file",
        "new request",
        "another",
        "same format",
        "template",
    ]
    local_repair_terms = [
        "fix only",
        "leave other fields empty",
        "patch",
        "verifier",
        "validator",
        "assertion",
        "field",
    ]
    search_terms = [
        "research",
        "search the web",
        "find upcoming",
        "market analysis",
        "competitive landscape",
        "current information",
    ]
    repo_debug_terms = [
        "repository",
        "repo",
        "build failure",
        "test failure",
        "migration",
        "debugging",
        "performance bug",
        "compile error",
    ]
    long_horizon_terms = [
        "prove",
        "optimize",
        "simulation",
        "clustering",
        "control",
        "scientific",
        "intrusion detection",
    ]

    def any_term(terms: list[str]) -> bool:
        return any(contains_term(normalized, term) for term in terms)

    if any_term(structured_output_terms):
        features["stable_output_format"] = 1
        reasons.append("Request specifies a stable output artifact or schema.")
    if any_term(stable_tool_terms):
        features["stable_tool_sequence"] = 1
        reasons.append("Request implies a stable read-transform-write workflow.")
    if any_term(substitution_terms):
        features["parameter_substitution"] = 1
        reasons.append("Task appears to vary mostly by slots or input values.")
    if any_term(local_repair_terms):
        features["local_validator_repair"] = 1
        reasons.append("Request includes local patch or validator-style constraints.")
    if any_term(search_terms):
        features["open_ended_search"] = 1
        reasons.append("Task requires open-ended search or broad retrieval.")
    if any_term(repo_debug_terms):
        features["repo_specific_debugging"] = 1
        reasons.append("Task looks repository-specific and debug-heavy.")
    if any_term(long_horizon_terms):
        features["long_horizon_reasoning"] = 1
        reasons.append("Task looks optimization-heavy or long-horizon.")

    return features, reasons


def family_score(
    family: dict[str, Any],
    task_id: str | None,
    request: str,
    feature_weights: dict[str, int],
    features: dict[str, int],
) -> tuple[int, list[str], list[str]]:
    score = int(family.get("score_bias", 0))
    matched_tasks: list[str] = []
    reasons: list[str] = []

    if task_id and task_id in family.get("tasks", []):
        score += 5
        matched_tasks.append(task_id)
        reasons.append(f"Exact task id matched `{task_id}`.")

    normalized_request = normalize(request)
    for keyword in family.get("keywords", []):
        if contains_term(normalized_request, keyword):
            score += 1
            reasons.append(f"Keyword match: `{keyword}`.")

    for feature_name, present in features.items():
        if present:
            score += feature_weights[feature_name]

    return score, matched_tasks, reasons


def choose_mode(score: int, preferred_mode: str | None) -> str:
    if preferred_mode == "full_model":
        return "full_model"
    if score >= 5:
        return "template_reuse" if preferred_mode == "template_reuse" else "macro_reuse"
    if score >= 2:
        return "macro_reuse"
    return "full_model"


def route_request(task_id: str | None, request: str) -> RouteDecision:
    catalog = load_catalog()
    feature_weights = catalog["feature_weights"]
    features, feature_reasons = infer_features(request or task_id or "")

    weighted_breakdown = {
        feature: feature_weights[feature] * value for feature, value in features.items() if value
    }

    best_family: dict[str, Any] | None = None
    best_score: int | None = None
    best_reasons: list[str] = []
    best_matched_tasks: list[str] = []

    candidate_families = catalog["families"]
    if task_id:
        exact_task_families = [family for family in candidate_families if task_id in family.get("tasks", [])]
        if exact_task_families:
            candidate_families = exact_task_families

    for family in candidate_families:
        score, matched_tasks, reasons = family_score(
            family=family,
            task_id=task_id,
            request=request,
            feature_weights=feature_weights,
            features=features,
        )
        if best_score is None or score > best_score:
            best_score = score
            best_family = family
            best_reasons = reasons
            best_matched_tasks = matched_tasks

    assert best_family is not None and best_score is not None

    mode = choose_mode(best_score, best_family.get("mode"))
    if mode == "template_reuse":
        fallback = "Execute the cached action program directly without an LLM; fall back on the first structural deviation."
    elif mode == "macro_reuse":
        fallback = "Execute the cached macro-actions directly; if execution reaches an uncovered step, stop reuse and hand the task to the full model."
    else:
        fallback = "Skip reuse and start with the stronger full-model policy."

    return RouteDecision(
        mode=mode,
        family_id=best_family["family_id"],
        template_name=best_family["template"]["name"] if mode != "full_model" else None,
        total_score=best_score,
        feature_breakdown=weighted_breakdown,
        matched_tasks=best_matched_tasks,
        reasons=best_reasons + feature_reasons,
        fallback=fallback,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Route a task into reuse or full-model execution.")
    parser.add_argument("--task-id", help="Known benchmark task id or task name.", default=None)
    parser.add_argument("--request", help="Free-form user request.", default="")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.task_id and not args.request:
        parser.error("Provide at least one of --task-id or --request.")

    decision = route_request(task_id=args.task_id, request=args.request)
    if args.pretty:
        print(json.dumps(decision.as_dict(), indent=2, ensure_ascii=True))
    else:
        print(json.dumps(decision.as_dict(), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
