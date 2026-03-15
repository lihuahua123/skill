#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

MODEL_ID="$(resolve_model "${1:-}")"
if [[ $# -gt 0 ]]; then
  shift
fi
EXTRA_ARGS=("$@")

SUITE_VALUE="$(default_suite)"
RUNS_VALUE="$(default_runs)"
RESULTS_DIR="${RQ4_RESULTS_DIR:-results/rq4}"
ANALYSIS_DIR="${RQ4_ANALYSIS_DIR:-analysis/rq4}"
CONTEXT_POLICY_VALUE="${RQ4_CONTEXT_POLICY:-append}"
STOP_RULE_VALUE="${RQ4_STOP_RULE:-max-attempts-only}"

for feedback_policy in vague error-localized actionable-path; do
  for feedback_format in full-refresh stable-prefix; do
    run_benchmark "${RESULTS_DIR}" \
      --model "${MODEL_ID}" \
      --suite "${SUITE_VALUE}" \
      --runs "${RUNS_VALUE}" \
      --max-task-attempts "${RQ4_MAX_ATTEMPTS:-5}" \
      --feedback-policy "${feedback_policy}" \
      --feedback-format "${feedback_format}" \
      --context-policy "${CONTEXT_POLICY_VALUE}" \
      --stop-rule "${STOP_RULE_VALUE}" \
      --stop-threshold "${RQ4_STOP_THRESHOLD:-0.0}" \
      "${EXTRA_ARGS[@]}"
  done
done

run_analysis "${RESULTS_DIR}" "${ANALYSIS_DIR}" "policy"
