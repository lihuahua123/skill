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
RESULTS_DIR="${RQ1_RESULTS_DIR:-results/rq1}"
ANALYSIS_DIR="${RQ1_ANALYSIS_DIR:-analysis/rq1}"

for attempts in 1 2 3 4 5 6; do
  run_benchmark "${RESULTS_DIR}" \
    --model "${MODEL_ID}" \
    --suite "${SUITE_VALUE}" \
    --runs "${RUNS_VALUE}" \
    --max-task-attempts "${attempts}" \
    --feedback-policy "${RQ1_FEEDBACK_POLICY:-error-localized}" \
    --feedback-format "${RQ1_FEEDBACK_FORMAT:-full-refresh}" \
    --context-policy "${RQ1_CONTEXT_POLICY:-append}" \
    --stop-rule "max-attempts-only" \
    "${EXTRA_ARGS[@]}"
done

run_analysis "${RESULTS_DIR}" "${ANALYSIS_DIR}" "policy"
