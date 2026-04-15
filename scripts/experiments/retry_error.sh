#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"
TASK_PATHS=(
  # tasks/adaptive-cruise-control 探索很久
  # tasks/earthquake-phase-association verify下载东西有问题
  # tasks/energy-ac-optimal-power-flow 探索很久
  tasks/energy-market-pricing
  tasks/exoplanet-detection-period
  tasks/financial-modeling-qa
  tasks/find-topk-similiar-chemicals
  tasks/fix-build-agentops
  tasks/fix-build-google-auto
  tasks/fix-druid-loophole-cve
  tasks/fix-erlang-ssh-cve
  tasks/fix-visual-stability
  tasks/flink-query
  tasks/gh-repo-analytics
  tasks/glm-lake-mendota
  tasks/grid-dispatch-operator
  tasks/invoice-fraud-detection
  tasks/jax-computing-basics
  tasks/jpg-ocr-stat
  tasks/lab-unit-harmonization
  tasks/lake-warming-attribution
  tasks/lean4-proof
  tasks/manufacturing-codebook-normalization
  tasks/manufacturing-equipment-maintenance
  tasks/manufacturing-fjsp-optimization
  tasks/mario-coin-counting
  tasks/mhc-layer-impl
  tasks/organize-messy-files
  tasks/parallel-tfidf-search
  tasks/pddl-tpp-planning
  tasks/pedestrian-traffic-counting
  tasks/pptx-reference-formatting
  tasks/python-scala-translation
  tasks/quantum-numerical-simulation
  tasks/react-performance-debugging
  tasks/reserves-at-risk-calc
  tasks/sales-pivot-analysis
  tasks/scheduling-email-assistant
  tasks/seismic-phase-picking
  tasks/setup-fuzzing-py
  tasks/shock-analysis-demand
  tasks/shock-analysis-supply
  tasks/software-dependency-audit
  tasks/suricata-custom-exfil
  tasks/syzkaller-ppdev-syzlang
  tasks/taxonomy-tree-merge
  tasks/threejs-to-obj
  tasks/video-silence-remover
  tasks/virtualhome-agent-planning
  tasks/weighted-gdp-calc
  tasks/xlsx-recover-data
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

TASKS_CSV="$(IFS=,; echo "${TASK_PATHS[*]}")"

NOISE_FILTER='Failed to fetch remote model cost map|Failed to retrieve model info for '\''anthropic/MiniMax-M2.7'\''|Provider List: https://docs.litellm.ai/docs/providers'
# RQ1_MAX_ATTEMPTS=1
nohup bash -lc '
  ./scripts/experiments/rq1.sh "'"${MINIMAX_MODEL:-anthropic/MiniMax-M2.5}"'" \
    --backend skillsbench \
    --max-parallel-tasks 2 \
    --skillsbench-task-path "'"${TASKS_CSV}"'" \
    2>&1 | grep -vE "'"${NOISE_FILTER}"'"
' > retry_error.log 2>&1 &

# --early_stop_intra_attempt \