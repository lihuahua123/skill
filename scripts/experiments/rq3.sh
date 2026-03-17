#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

MODEL_ARGS=()
if [[ $# -gt 0 && "${1}" != -* ]]; then
  MODEL_ARGS=(--model "$1")
  shift
elif option_supplied --model "$@"; then
  :
elif [[ -n "${MODEL:-}" ]]; then
  MODEL_ARGS=(--model "${MODEL}")
else
  echo "Usage: $0 MODEL [extra benchmark args...]" >&2
  echo "Or pass --model MODEL_ID, or set MODEL in the environment." >&2
  exit 2
fi
EXTRA_ARGS=("$@")

SUITE_ARGS=()
if ! option_supplied --suite "${EXTRA_ARGS[@]}"; then
  SUITE_ARGS=(--suite "$(default_suite)")
fi

RUNS_ARGS=()
if ! option_supplied --runs "${EXTRA_ARGS[@]}"; then
  RUNS_ARGS=(--runs "$(default_runs)")
fi

RESULTS_DIR="${RQ3_RESULTS_DIR:-results/rq3}"
ANALYSIS_DIR="${RQ3_ANALYSIS_DIR:-analysis/rq3}"
CONTEXT_POLICY_VALUE="${RQ3_CONTEXT_POLICY:-append}"
MAX_ATTEMPTS_VALUE="${RQ3_MAX_ATTEMPTS:-5}"

run_benchmark "${RESULTS_DIR}" \
  "${MODEL_ARGS[@]}" \
  "${SUITE_ARGS[@]}" \
  "${RUNS_ARGS[@]}" \
  --max-task-attempts "${MAX_ATTEMPTS_VALUE}" \
  --feedback-policy "${RQ3_FEEDBACK_POLICY:-error-localized}" \
  --feedback-format "${RQ3_FEEDBACK_FORMAT:-full-refresh}" \
  --context-policy "${CONTEXT_POLICY_VALUE}" \
  --stop-rule "max-attempts-only" \
  "${EXTRA_ARGS[@]}"

latest_json="$(latest_result_json "${RESULTS_DIR}")"
if [[ -n "${latest_json}" ]] && result_has_perfect_success "${latest_json}"; then
  echo "RQ3 early stop: suite success already reached 100% at fixed budget" >&2
  run_analysis "${RESULTS_DIR}" "${ANALYSIS_DIR}" "policy"
  exit 0
fi

run_benchmark "${RESULTS_DIR}" \
  "${MODEL_ARGS[@]}" \
  "${SUITE_ARGS[@]}" \
  "${RUNS_ARGS[@]}" \
  --max-task-attempts "${MAX_ATTEMPTS_VALUE}" \
  --feedback-policy "${RQ3_FEEDBACK_POLICY:-error-localized}" \
  --feedback-format "${RQ3_FEEDBACK_FORMAT:-full-refresh}" \
  --context-policy "${CONTEXT_POLICY_VALUE}" \
  --stop-rule "score-stall" \
  --stop-threshold "${RQ3_SCORE_STALL_THRESHOLD:-0.0}" \
  "${EXTRA_ARGS[@]}"

run_benchmark "${RESULTS_DIR}" \
  "${MODEL_ARGS[@]}" \
  "${SUITE_ARGS[@]}" \
  "${RUNS_ARGS[@]}" \
  --max-task-attempts "${MAX_ATTEMPTS_VALUE}" \
  --feedback-policy "${RQ3_FEEDBACK_POLICY:-error-localized}" \
  --feedback-format "${RQ3_FEEDBACK_FORMAT:-full-refresh}" \
  --context-policy "${CONTEXT_POLICY_VALUE}" \
  --stop-rule "unresolved-stall" \
  "${EXTRA_ARGS[@]}"

run_benchmark "${RESULTS_DIR}" \
  "${MODEL_ARGS[@]}" \
  "${SUITE_ARGS[@]}" \
  "${RUNS_ARGS[@]}" \
  --max-task-attempts "${MAX_ATTEMPTS_VALUE}" \
  --feedback-policy "${RQ3_FEEDBACK_POLICY:-error-localized}" \
  --feedback-format "${RQ3_FEEDBACK_FORMAT:-full-refresh}" \
  --context-policy "${CONTEXT_POLICY_VALUE}" \
  --stop-rule "low-return" \
  --stop-threshold "${RQ3_LOW_RETURN_THRESHOLD:-0.01}" \
  "${EXTRA_ARGS[@]}"

run_analysis "${RESULTS_DIR}" "${ANALYSIS_DIR}" "policy"
