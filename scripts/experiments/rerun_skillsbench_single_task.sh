#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"

MODEL="${MODEL:-anthropic/MiniMax-M2.5}"
TASK_NAME="fix-build-google-auto"
TASK_PATH="${TASK_PATH:-tasks/${TASK_NAME}}"
RUNS="${RUNS:-1}"
MAX_TASK_ATTEMPTS="${MAX_TASK_ATTEMPTS:-4}"
MAX_PARALLEL_TASKS="${MAX_PARALLEL_TASKS:-1}"
PAPER_INITIAL_TURN_LIMIT="${PAPER_INITIAL_TURN_LIMIT:-14}"
PAPER_EXTENSION_TURN_LIMIT="${PAPER_EXTENSION_TURN_LIMIT:-14}"
PAPER_REMIND_EVERY_TURN="${PAPER_REMIND_EVERY_TURN:-false}"
STOP_CHECK_EARLY_STOP_ENABLED="${STOP_CHECK_EARLY_STOP_ENABLED:-false}" # 这个如果zero_PROGRESS_STREAK很少的话，是真的很没用啊, 即使加了也很没用，反而增大轮次了
STOP_CHECK_ZERO_PROGRESS_STREAK="${STOP_CHECK_ZERO_PROGRESS_STREAK:-10}"
STOP_CHECK_YES_STREAK="${STOP_CHECK_YES_STREAK:-2}"
SKILLSBENCH_SKILL_GUIDANCE="${SKILLSBENCH_SKILL_GUIDANCE:-true}" # 有点用
INJECT_TOKEN_EFFICIENT_TRIAGE_FIRST_PROMPT="${INJECT_TOKEN_EFFICIENT_TRIAGE_FIRST_PROMPT:-false}" # 这个是真的没用啊
RETRY_WORKSPACE_STRATEGY="${RETRY_WORKSPACE_STRATEGY:-preserve}" #fresh
FORCE_BUILD="${FORCE_BUILD:-false}"
RUN_STAMP="$(date +"%Y-%m-%d__%H-%M-%S")"
RUN_ID="${RUN_ID:-${TASK_NAME}-paper-dynamic-turn-${RUN_STAMP}}"
JOB_NAME="${JOB_NAME:-skillsbench-${RUN_ID}}"

NOISE_FILTER='Failed to fetch remote model cost map|Failed to retrieve model info for '\''anthropic/MiniMax-M2.7'\''|Provider List: https://docs.litellm.ai/docs/providers'

CMD=(
  ./scripts/experiments/rq1.sh "${MODEL}"
  --backend skillsbench
  --runs "${RUNS}"
  --max-task-attempts "${MAX_TASK_ATTEMPTS}"
  --max-parallel-tasks "${MAX_PARALLEL_TASKS}"
  --run-id "${RUN_ID}"
  --job-name "${JOB_NAME}"
  --skillsbench-task-path "${TASK_PATH}"
  --skillsbench-skill-guidance "${SKILLSBENCH_SKILL_GUIDANCE}"
  --retry-workspace-strategy "${RETRY_WORKSPACE_STRATEGY}"
  --inject-token-efficient-triage-first-prompt "${INJECT_TOKEN_EFFICIENT_TRIAGE_FIRST_PROMPT}"
  --ak "paper_dynamic_turn_enabled=false"
)

if [[ "${STOP_CHECK_EARLY_STOP_ENABLED,,}" == "1" || "${STOP_CHECK_EARLY_STOP_ENABLED,,}" == "true" || "${STOP_CHECK_EARLY_STOP_ENABLED,,}" == "yes" ]]; then
  CMD+=(
    --ak "paper_turn_stopcheck_enabled=true"
    --ak "paper_turn_stopcheck_zero_progress_streak=${STOP_CHECK_ZERO_PROGRESS_STREAK}"
    --ak "paper_turn_stopcheck_yes_streak=${STOP_CHECK_YES_STREAK}"
  )
fi

if [[ "${FORCE_BUILD,,}" == "1" || "${FORCE_BUILD,,}" == "true" || "${FORCE_BUILD,,}" == "yes" ]]; then
  CMD+=(--force-build)
fi

if [[ $# -gt 0 ]]; then
  CMD+=("$@")
fi

echo "Running command:"
printf ' %q' "${CMD[@]}"
printf '\n'

set +o pipefail
"${CMD[@]}" 2>&1 | grep -vE "${NOISE_FILTER}"
status=${PIPESTATUS[0]}
set -o pipefail

exit "${status}"
