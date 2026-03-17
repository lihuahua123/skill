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

RESULTS_DIR="${RQ4_RESULTS_DIR:-results/rq4}"
ANALYSIS_DIR="${RQ4_ANALYSIS_DIR:-analysis/rq4}"
CONTEXT_POLICY_VALUE="${RQ4_CONTEXT_POLICY:-append}"
STOP_RULE_VALUE="${RQ4_STOP_RULE:-max-attempts-only}"

for feedback_policy in vague error-localized actionable-path; do
  for feedback_format in full-refresh stable-prefix; do
    run_benchmark "${RESULTS_DIR}" \
      "${MODEL_ARGS[@]}" \
      "${SUITE_ARGS[@]}" \
      "${RUNS_ARGS[@]}" \
      --max-task-attempts "${RQ4_MAX_ATTEMPTS:-2}" \
      --feedback-policy "${feedback_policy}" \
      --feedback-format "${feedback_format}" \
      --context-policy "${CONTEXT_POLICY_VALUE}" \
      --stop-rule "${STOP_RULE_VALUE}" \
      --stop-threshold "${RQ4_STOP_THRESHOLD:-0.0}" \
      "${EXTRA_ARGS[@]}"
  done
done

run_analysis "${RESULTS_DIR}" "${ANALYSIS_DIR}" "policy"
