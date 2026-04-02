#!/usr/bin/env python3
"""Detect reuse failure and recommend whether to continue reuse or abort to fallback."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RULES_PATH = ROOT / "failure_rules.json"


@dataclass
class FailureDecision:
    decision: str
    triggered_rules: list[dict[str, Any]]
    summary: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "triggered_rules": self.triggered_rules,
            "summary": self.summary,
        }


def load_rules() -> dict[str, Any]:
    return json.loads(RULES_PATH.read_text())


def evaluate_reuse_failure(runtime: dict[str, Any]) -> FailureDecision:
    config = load_rules()
    thresholds = config["thresholds"]
    triggered: list[dict[str, Any]] = []
    summary: list[str] = []

    family_score = int(runtime.get("family_score", 0))
    family_score_gap = int(runtime.get("family_score_gap", 999))
    missing_slots_count = int(runtime.get("missing_slots_count", 0))
    output_contract_passed = bool(runtime.get("output_contract_passed", True))
    missing_intermediate_artifacts_count = int(runtime.get("missing_intermediate_artifacts_count", 0))
    validator_error_expected = bool(runtime.get("validator_error_expected", True))
    trajectory_deviation_score = float(runtime.get("trajectory_deviation_score", 0.0))
    token_ratio_to_template_mean = float(runtime.get("token_ratio_to_template_mean", 1.0))
    time_ratio_to_template_mean = float(runtime.get("time_ratio_to_template_mean", 1.0))
    repair_progress_stalled = bool(runtime.get("repair_progress_stalled", False))

    if missing_slots_count > 0:
        triggered.append(next(rule for rule in config["rules"] if rule["rule_id"] == "missing_required_slots"))
        summary.append("Required template slots are missing, so reuse cannot be safely instantiated.")

    if (
        family_score < thresholds["template_reuse_min_family_score"]
        or family_score_gap <= thresholds["max_family_score_gap_for_ambiguity"]
    ):
        triggered.append(next(rule for rule in config["rules"] if rule["rule_id"] == "ambiguous_family_match"))
        summary.append("Family match is weak or ambiguous, so direct template reuse is unsafe.")

    if not output_contract_passed:
        triggered.append(next(rule for rule in config["rules"] if rule["rule_id"] == "output_contract_failed"))
        summary.append("Observed output does not satisfy the requested contract.")

    if missing_intermediate_artifacts_count > 0:
        triggered.append(next(rule for rule in config["rules"] if rule["rule_id"] == "missing_intermediate_artifact"))
        summary.append("A required intermediate artifact is missing at the current checkpoint.")

    if not validator_error_expected:
        triggered.append(next(rule for rule in config["rules"] if rule["rule_id"] == "unexpected_validator_error_class"))
        summary.append("Validator feedback falls outside the error class covered by the selected template.")

    if trajectory_deviation_score > thresholds["max_trajectory_deviation_score"]:
        triggered.append(next(rule for rule in config["rules"] if rule["rule_id"] == "trajectory_deviation"))
        summary.append("Observed action trajectory deviates too far from the family skeleton.")

    if (
        token_ratio_to_template_mean > thresholds["max_token_ratio_to_template_mean"]
        or time_ratio_to_template_mean > thresholds["max_time_ratio_to_template_mean"]
    ):
        triggered.append(next(rule for rule in config["rules"] if rule["rule_id"] == "budget_anomaly"))
        summary.append("Runtime budget is far above the normal range for this template before success.")

    if repair_progress_stalled:
        triggered.append(next(rule for rule in config["rules"] if rule["rule_id"] == "no_progress_across_repairs"))
        summary.append("Patch attempts are stalling without improving the failure state.")

    decision = "abort_and_fallback" if triggered else "continue_reuse"
    if not summary:
        summary.append("No failure rules triggered; continue the current reuse policy.")

    return FailureDecision(decision=decision, triggered_rules=triggered, summary=summary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect whether reuse should continue or abort.")
    parser.add_argument(
        "--runtime-json",
        help="Inline JSON object describing runtime signals.",
        default=None,
    )
    parser.add_argument(
        "--runtime-file",
        help="Path to a JSON file describing runtime signals.",
        default=None,
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    return parser


def load_runtime(args: argparse.Namespace) -> dict[str, Any]:
    if args.runtime_json:
        return json.loads(args.runtime_json)
    if args.runtime_file:
        return json.loads(Path(args.runtime_file).read_text())
    raise SystemExit("Provide either --runtime-json or --runtime-file.")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    runtime = load_runtime(args)
    decision = evaluate_reuse_failure(runtime)
    if args.pretty:
        print(json.dumps(decision.as_dict(), indent=2, ensure_ascii=True))
    else:
        print(json.dumps(decision.as_dict(), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
