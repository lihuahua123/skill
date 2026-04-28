#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${SCRIPT_DIR}/common.sh"

cd "${REPO_ROOT}"

SKILLSBENCH_MODE="${SKILLSBENCH_MODE:-with-skills}"
TASK_PREFIX="$(skillsbench_tasks_prefix "${SKILLSBENCH_MODE}")"
TASKS_ROOT="$(skillsbench_tasks_root "${SKILLSBENCH_MODE}")"

mapfile -t DISCOVERED_TASK_DIRS < <(
  find "${TASKS_ROOT}" -mindepth 1 -maxdepth 1 -type d | sort
)

TASK_PATHS=()
for task_dir in "${DISCOVERED_TASK_DIRS[@]}"; do
  TASK_PATHS+=("${TASK_PREFIX}/$(basename "${task_dir}")")
done

filter_task_if_missing_env() {
  local missing_env="$1"
  local filtered_task="$2"

  if [[ -n "${!missing_env:-}" ]]; then
    return 0
  fi

  local remaining_tasks=()
  local task
  for task in "${TASK_PATHS[@]}"; do
    if [[ "${task}" != "${filtered_task}" ]]; then
      remaining_tasks+=("${task}")
    fi
  done
  TASK_PATHS=("${remaining_tasks[@]}")
}

filter_task_if_missing_env "MODAL_TOKEN_ID" "tasks/mhc-layer-impl"
filter_task_if_missing_env "MODAL_TOKEN_SECRET" "tasks/mhc-layer-impl"
filter_task_if_missing_env "OPENAI_API_KEY" "tasks/pedestrian-traffic-counting"
filter_task_if_missing_env "GH_TOKEN" "tasks/gh-repo-analytics"
filter_task_if_missing_env "GOOGLE_AUTH_PATH" "tasks/scheduling-email-assistant"

NOISE_FILTER='Failed to fetch remote model cost map|Failed to retrieve model info for '\''anthropic/MiniMax-M2.7'\''|Provider List: https://docs.litellm.ai/docs/providers'

MODEL="${MINIMAX_MODEL:-anthropic/MiniMax-M2.5}"
MAX_PARALLEL_TASKS="${RQ1_MAX_PARALLEL_TASKS:-2}"
RUN_STAMP="$(date +"%Y-%m-%d__%H-%M-%S")"
MAIN_LOG="${REPO_ROOT}/rq1_all_tasks.log"
TASK_LOG_DIR="${REPO_ROOT}/logs/rq1_all_tasks/${RUN_STAMP}"

mkdir -p "${TASK_LOG_DIR}"

run_task() {
  local task="$1"
  local task_name="${task##*/}"
  local run_id="rq1-all-${RUN_STAMP}-${task_name}"
  local task_log="${TASK_LOG_DIR}/${task_name}.log"
  local status=0

  {
    echo "[$(date +"%F %T")] START ${task}"
    set +o pipefail
    ./scripts/experiments/rq1.sh "${MODEL}" \
      --backend skillsbench \
      --max-parallel-tasks 1 \
      --run-id "${run_id}" \
      --job-name "skillsbench-${run_id}" \
      --skillsbench-task-path "${task}" \
      2>&1 | grep -vE "${NOISE_FILTER}"
    status=${PIPESTATUS[0]}
    set -o pipefail
    if [[ ${status} -eq 0 ]]; then
      echo "[$(date +"%F %T")] SUCCESS ${task}"
    else
      echo "[$(date +"%F %T")] FAIL(${status}) ${task}"
    fi
  } > "${task_log}" 2>&1

  return 0
}

(
  set -euo pipefail
  echo "[$(date +"%F %T")] started rq1_all_tasks runner"
  echo "model=${MODEL}"
  echo "skillsbench_mode=${SKILLSBENCH_MODE}"
  echo "max_parallel_tasks=${MAX_PARALLEL_TASKS}"
  echo "task_count=${#TASK_PATHS[@]}"
  echo "task_logs=${TASK_LOG_DIR}"

  active_jobs=0
  for task in "${TASK_PATHS[@]}"; do
    echo "[$(date +"%F %T")] QUEUE ${task}"
    run_task "${task}" &
    ((active_jobs += 1))
    if (( active_jobs >= MAX_PARALLEL_TASKS )); then
      wait -n || true
      ((active_jobs -= 1))
    fi
  done

  while (( active_jobs > 0 )); do
    wait -n || true
    ((active_jobs -= 1))
  done

  echo "[$(date +"%F %T")] finished rq1_all_tasks runner"
) > "${MAIN_LOG}" 2>&1 < /dev/null &
