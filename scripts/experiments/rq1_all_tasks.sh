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

MODEL="${MINIMAX_MODEL:-anthropic/MiniMax-M2.7}"
RUNS="${RUNS:-1}"
MAX_TASK_ATTEMPTS="${MAX_TASK_ATTEMPTS:-6}"
MAX_PARALLEL_TASKS="${RQ1_MAX_PARALLEL_TASKS:-2}"
PAPER_INITIAL_TURN_LIMIT="${PAPER_INITIAL_TURN_LIMIT:-14}"
PAPER_EXTENSION_TURN_LIMIT="${PAPER_EXTENSION_TURN_LIMIT:-14}"
PAPER_REMIND_EVERY_TURN="${PAPER_REMIND_EVERY_TURN:-true}"
STOP_CHECK_EARLY_STOP_ENABLED="${STOP_CHECK_EARLY_STOP_ENABLED:-true}"
STOP_CHECK_ZERO_PROGRESS_STREAK="${STOP_CHECK_ZERO_PROGRESS_STREAK:-2}"
STOP_CHECK_YES_STREAK="${STOP_CHECK_YES_STREAK:-2}"
SKILLSBENCH_SKILL_GUIDANCE="${SKILLSBENCH_SKILL_GUIDANCE:-false}"
FORCE_BUILD="${FORCE_BUILD:-false}"
RUN_STAMP="$(date +"%Y-%m-%d__%H-%M-%S")"
RUN_OUTPUT_DIR="${REPO_ROOT}/logs/rq1_all_tasks/${RUN_STAMP}"
RUN_JOB_GROUP="skillsbench-rq1-all-${RUN_STAMP}"
MAIN_LOG="${REPO_ROOT}/rq1_all_tasks.log"
TASK_LOG_DIR="${RUN_OUTPUT_DIR}/task_logs"
JOBS_ROOT="${JOBS_ROOT:-${REPO_ROOT}/skillsbench/jobs/${RUN_JOB_GROUP}}"

mkdir -p "${TASK_LOG_DIR}" "${JOBS_ROOT}"

is_truthy() {
  local value="${1,,}"
  [[ "${value}" == "1" || "${value}" == "true" || "${value}" == "yes" ]]
}

run_task() {
  local task="$1"
  local task_name="${task##*/}"
  local run_id="rq1-all-${RUN_STAMP}-${task_name}"
  local job_name="skillsbench-${run_id}"
  local task_log="${TASK_LOG_DIR}/${task_name}.log"
  local status=0
  local -a cmd=(
    ./scripts/experiments/rq1.sh "${MODEL}"
    --backend skillsbench
    --runs "${RUNS}"
    --max-task-attempts "${MAX_TASK_ATTEMPTS}"
    --max-parallel-tasks 1
    --run-id "${run_id}"
    --job-name "${job_name}"
    --jobs-root "${JOBS_ROOT}"
    --skillsbench-task-path "${task}"
    --skillsbench-skill-guidance "${SKILLSBENCH_SKILL_GUIDANCE}"
    --ak "paper_dynamic_turn_enabled=false"
    --ak "paper_initial_turn_limit=${PAPER_INITIAL_TURN_LIMIT}"
    --ak "paper_extension_turn_limit=${PAPER_EXTENSION_TURN_LIMIT}"
    --ak "paper_remind_every_turn=${PAPER_REMIND_EVERY_TURN}"
  )

  if is_truthy "${STOP_CHECK_EARLY_STOP_ENABLED}"; then
    cmd+=(
      --ak "paper_turn_stopcheck_enabled=true"
      --ak "paper_turn_stopcheck_zero_progress_streak=${STOP_CHECK_ZERO_PROGRESS_STREAK}"
      --ak "paper_turn_stopcheck_yes_streak=${STOP_CHECK_YES_STREAK}"
    )
  fi

  if is_truthy "${FORCE_BUILD}"; then
    cmd+=(--force-build)
  fi

  {
    echo "[$(date +"%F %T")] START ${task}"
    printf 'command:'
    printf ' %q' "${cmd[@]}"
    printf '\n'
    set +o pipefail
    "${cmd[@]}" 2>&1 | grep -vE "${NOISE_FILTER}"
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
  echo "runs=${RUNS}"
  echo "max_task_attempts=${MAX_TASK_ATTEMPTS}"
  echo "max_parallel_tasks=${MAX_PARALLEL_TASKS}"
  echo "paper_initial_turn_limit=${PAPER_INITIAL_TURN_LIMIT}"
  echo "paper_extension_turn_limit=${PAPER_EXTENSION_TURN_LIMIT}"
  echo "paper_remind_every_turn=${PAPER_REMIND_EVERY_TURN}"
  echo "stop_check_early_stop_enabled=${STOP_CHECK_EARLY_STOP_ENABLED}"
  echo "stop_check_zero_progress_streak=${STOP_CHECK_ZERO_PROGRESS_STREAK}"
  echo "stop_check_yes_streak=${STOP_CHECK_YES_STREAK}"
  echo "skillsbench_skill_guidance=${SKILLSBENCH_SKILL_GUIDANCE}"
  echo "force_build=${FORCE_BUILD}"
  echo "task_count=${#TASK_PATHS[@]}"
  echo "run_job_group=${RUN_JOB_GROUP}"
  echo "run_output_dir=${RUN_OUTPUT_DIR}"
  echo "task_logs=${TASK_LOG_DIR}"
  echo "jobs_root=${JOBS_ROOT}"

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
