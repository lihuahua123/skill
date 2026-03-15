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
RESULTS_DIR="${RQ2_RESULTS_DIR:-results/rq2}"
ANALYSIS_DIR="${RQ2_ANALYSIS_DIR:-analysis/rq2}"

for context_policy in append fresh-session rollback; do
  run_benchmark "${RESULTS_DIR}" \
    --model "${MODEL_ID}" \
    --suite "${SUITE_VALUE}" \
    --runs "${RUNS_VALUE}" \
    --max-task-attempts "${RQ2_MAX_ATTEMPTS:-5}" \
    --feedback-policy "${RQ2_FEEDBACK_POLICY:-error-localized}" \
    --feedback-format "${RQ2_FEEDBACK_FORMAT:-full-refresh}" \
    --context-policy "${context_policy}" \
    --stop-rule "max-attempts-only" \
    "${EXTRA_ARGS[@]}"
done

run_analysis "${RESULTS_DIR}" "${ANALYSIS_DIR}" "policy"
