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

RESULTS_DIR="${RQ2_RESULTS_DIR:-results/rq2}"
ANALYSIS_DIR="${RQ2_ANALYSIS_DIR:-analysis/rq2}"

for context_policy in append fresh-session rollback; do
  run_benchmark "${RESULTS_DIR}" \
    "${MODEL_ARGS[@]}" \
    "${SUITE_ARGS[@]}" \
    "${RUNS_ARGS[@]}" \
    --max-task-attempts "${RQ2_MAX_ATTEMPTS:-2}" \
    --feedback-policy "${RQ2_FEEDBACK_POLICY:-error-localized}" \
    --feedback-format "${RQ2_FEEDBACK_FORMAT:-full-refresh}" \
    --context-policy "${context_policy}" \
    --stop-rule "max-attempts-only" \
    "${EXTRA_ARGS[@]}"
done

run_analysis "${RESULTS_DIR}" "${ANALYSIS_DIR}" "policy"
