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
RESULTS_DIR="${RQ3_RESULTS_DIR:-results/rq3}"
ANALYSIS_DIR="${RQ3_ANALYSIS_DIR:-analysis/rq3}"
CONTEXT_POLICY_VALUE="${RQ3_CONTEXT_POLICY:-append}"

run_benchmark "${RESULTS_DIR}" \
  --model "${MODEL_ID}" \
  --suite "${SUITE_VALUE}" \
  --runs "${RUNS_VALUE}" \
  --max-task-attempts "3" \
  --feedback-policy "${RQ3_FEEDBACK_POLICY:-error-localized}" \
  --feedback-format "${RQ3_FEEDBACK_FORMAT:-full-refresh}" \
  --context-policy "${CONTEXT_POLICY_VALUE}" \
  --stop-rule "max-attempts-only" \
  "${EXTRA_ARGS[@]}"

run_benchmark "${RESULTS_DIR}" \
  --model "${MODEL_ID}" \
  --suite "${SUITE_VALUE}" \
  --runs "${RUNS_VALUE}" \
  --max-task-attempts "5" \
  --feedback-policy "${RQ3_FEEDBACK_POLICY:-error-localized}" \
  --feedback-format "${RQ3_FEEDBACK_FORMAT:-full-refresh}" \
  --context-policy "${CONTEXT_POLICY_VALUE}" \
  --stop-rule "max-attempts-only" \
  "${EXTRA_ARGS[@]}"

run_benchmark "${RESULTS_DIR}" \
  --model "${MODEL_ID}" \
  --suite "${SUITE_VALUE}" \
  --runs "${RUNS_VALUE}" \
  --max-task-attempts "${RQ3_MAX_ATTEMPTS:-5}" \
  --feedback-policy "${RQ3_FEEDBACK_POLICY:-error-localized}" \
  --feedback-format "${RQ3_FEEDBACK_FORMAT:-full-refresh}" \
  --context-policy "${CONTEXT_POLICY_VALUE}" \
  --stop-rule "score-stall" \
  --stop-threshold "${RQ3_SCORE_STALL_THRESHOLD:-0.0}" \
  "${EXTRA_ARGS[@]}"

run_benchmark "${RESULTS_DIR}" \
  --model "${MODEL_ID}" \
  --suite "${SUITE_VALUE}" \
  --runs "${RUNS_VALUE}" \
  --max-task-attempts "${RQ3_MAX_ATTEMPTS:-5}" \
  --feedback-policy "${RQ3_FEEDBACK_POLICY:-error-localized}" \
  --feedback-format "${RQ3_FEEDBACK_FORMAT:-full-refresh}" \
  --context-policy "${CONTEXT_POLICY_VALUE}" \
  --stop-rule "unresolved-stall" \
  "${EXTRA_ARGS[@]}"

run_benchmark "${RESULTS_DIR}" \
  --model "${MODEL_ID}" \
  --suite "${SUITE_VALUE}" \
  --runs "${RUNS_VALUE}" \
  --max-task-attempts "${RQ3_MAX_ATTEMPTS:-5}" \
  --feedback-policy "${RQ3_FEEDBACK_POLICY:-error-localized}" \
  --feedback-format "${RQ3_FEEDBACK_FORMAT:-full-refresh}" \
  --context-policy "${CONTEXT_POLICY_VALUE}" \
  --stop-rule "low-return" \
  --stop-threshold "${RQ3_LOW_RETURN_THRESHOLD:-0.01}" \
  "${EXTRA_ARGS[@]}"

run_analysis "${RESULTS_DIR}" "${ANALYSIS_DIR}" "policy"
