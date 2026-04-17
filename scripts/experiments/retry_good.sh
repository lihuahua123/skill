#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"
TASK_PATHS=(
  tasks/3d-scan-calc
  tasks/azure-bgp-oscillation-route-leak
  tasks/citation-check
  tasks/civ6-adjacency-optimizer
  tasks/court-form-filling
  tasks/crystallographic-wyckoff-position-analysis
  tasks/dapt-intrusion-detection
  tasks/data-to-d3
  tasks/dialogue-parser
  tasks/dynamic-object-aware-egomotion
  tasks/earthquake-plate-calculation
  tasks/econ-detrending-correlation
  tasks/enterprise-information-search
  tasks/exceltable-in-ppt
  tasks/flood-risk-analysis
  tasks/gravitational-wave-detection
  tasks/hvac-control
  tasks/latex-formula-extraction
  tasks/mars-clouds-clustering
  tasks/multilingual-video-dubbing
  tasks/offer-letter-generator
  tasks/paper-anonymizer
  tasks/pdf-excel-diff
  tasks/pg-essay-to-audiobook
  tasks/powerlifting-coef-calc
  tasks/protein-expression-analysis
  tasks/r2r-mpc-control
  tasks/sec-financial-report
  tasks/simpo-code-reproduction
  tasks/speaker-diarization-subtitles
  tasks/spring-boot-jakarta-migration
  tasks/threejs-structure-parser
  tasks/travel-planning
  tasks/trend-anomaly-causal-inference
  tasks/video-filler-word-remover
  tasks/video-tutorial-indexer
)

if [[ -z "${MODAL_TOKEN_ID:-}" || -z "${MODAL_TOKEN_SECRET:-}" ]]; then
  FILTERED_TASKS=()
  for task in "${TASK_PATHS[@]}"; do
    if [[ "${task}" != "tasks/mhc-layer-impl" ]]; then
      FILTERED_TASKS+=("${task}")
    fi
  done
  TASK_PATHS=("${FILTERED_TASKS[@]}")
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  FILTERED_TASKS=()
  for task in "${TASK_PATHS[@]}"; do
    if [[ "${task}" != "tasks/pedestrian-traffic-counting" ]]; then
      FILTERED_TASKS+=("${task}")
    fi
  done
  TASK_PATHS=("${FILTERED_TASKS[@]}")
fi

if [[ -z "${GH_TOKEN:-}" ]]; then
  FILTERED_TASKS=()
  for task in "${TASK_PATHS[@]}"; do
    if [[ "${task}" != "tasks/gh-repo-analytics" ]]; then
      FILTERED_TASKS+=("${task}")
    fi
  done
  TASK_PATHS=("${FILTERED_TASKS[@]}")
fi

if [[ -z "${GOOGLE_AUTH_PATH:-}" ]]; then
  FILTERED_TASKS=()
  for task in "${TASK_PATHS[@]}"; do
    if [[ "${task}" != "tasks/scheduling-email-assistant" ]]; then
      FILTERED_TASKS+=("${task}")
    fi
  done
  TASK_PATHS=("${FILTERED_TASKS[@]}")
fi

NOISE_FILTER='Failed to fetch remote model cost map|Failed to retrieve model info for '\''anthropic/MiniMax-M2.7'\''|Provider List: https://docs.litellm.ai/docs/providers'

MODEL="${MINIMAX_MODEL:-anthropic/MiniMax-M2.5}"
MAX_PARALLEL_TASKS="${RQ1_MAX_PARALLEL_TASKS:-2}"
RUN_STAMP="$(date +"%Y-%m-%d__%H-%M-%S")"
MAIN_LOG="${REPO_ROOT}/retry_good.log"
TASK_LOG_DIR="${REPO_ROOT}/logs/retry_good/${RUN_STAMP}"

mkdir -p "${TASK_LOG_DIR}"

run_task() {
  local task="$1"
  local task_name="${task##*/}"
  local run_id="retry-good-${RUN_STAMP}-${task_name}"
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
  echo "[$(date +"%F %T")] started retry_good runner"
  echo "model=${MODEL}"
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

  echo "[$(date +"%F %T")] finished retry_good runner"
) > "${MAIN_LOG}" 2>&1 < /dev/null &

# --early_stop_intra_attempt
