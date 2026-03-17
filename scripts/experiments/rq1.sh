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

RESULTS_DIR="${RQ1_RESULTS_DIR:-results/rq1}"
ANALYSIS_DIR="${RQ1_ANALYSIS_DIR:-analysis/rq1}"
MAX_ATTEMPTS_VALUE="${RQ1_MAX_ATTEMPTS:-2}"

run_benchmark "${RESULTS_DIR}" \
  "${MODEL_ARGS[@]}" \
  "${SUITE_ARGS[@]}" \
  "${RUNS_ARGS[@]}" \
  --max-task-attempts "${MAX_ATTEMPTS_VALUE}" \
  --feedback-policy "${RQ1_FEEDBACK_POLICY:-error-localized}" \
  --feedback-format "${RQ1_FEEDBACK_FORMAT:-full-refresh}" \
  --context-policy "${RQ1_CONTEXT_POLICY:-append}" \
  --stop-rule "max-attempts-only" \
  "${EXTRA_ARGS[@]}"

run_analysis "${RESULTS_DIR}" "${ANALYSIS_DIR}" "policy"
# --model minimax-cn/MiniMax-M2.5 --suite task_06_events
