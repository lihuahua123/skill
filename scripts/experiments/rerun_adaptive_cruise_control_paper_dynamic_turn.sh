#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"

MODEL="${MODEL:-anthropic/MiniMax-M2.7}"
TASK_PATH="${TASK_PATH:-tasks/adaptive-cruise-control}"
RUNS="${RUNS:-1}"
MAX_TASK_ATTEMPTS="${MAX_TASK_ATTEMPTS:-6}"
MAX_PARALLEL_TASKS="${MAX_PARALLEL_TASKS:-1}"
PAPER_INITIAL_TURN_LIMIT="${PAPER_INITIAL_TURN_LIMIT:-14}"
PAPER_EXTENSION_TURN_LIMIT="${PAPER_EXTENSION_TURN_LIMIT:-14}"
PAPER_REMIND_EVERY_TURN="${PAPER_REMIND_EVERY_TURN:-true}"
SKILLSBENCH_SKILL_GUIDANCE="${SKILLSBENCH_SKILL_GUIDANCE:-false}"
FORCE_BUILD="${FORCE_BUILD:-false}"
RUN_STAMP="$(date +"%Y-%m-%d__%H-%M-%S")"
RUN_ID="${RUN_ID:-adaptive-cruise-control-paper-dynamic-turn-${RUN_STAMP}}"
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
  --ak "paper_dynamic_turn_enabled=false"
  # --ak "paper_dynamic_turn_initial_turn_limit=${PAPER_INITIAL_TURN_LIMIT}"
  # --ak "paper_dynamic_turn_extension_turn_limit=${PAPER_EXTENSION_TURN_LIMIT}"
  # --ak "paper_dynamic_turn_remind_every_turn=${PAPER_REMIND_EVERY_TURN}"
)

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
