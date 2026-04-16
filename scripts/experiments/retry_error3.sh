#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"
TASK_PATHS=(
  # Network failures in skillsbench-2026-04-16__08-46-05
  # Pattern: docker image metadata fetch failed with proxyconnect i/o timeout
  tasks/energy-market-pricing
  tasks/fix-visual-stability
  tasks/flink-query
  tasks/grid-dispatch-operator
  tasks/invoice-fraud-detection
  tasks/jax-computing-basics
  tasks/manufacturing-fjsp-optimization
  tasks/python-scala-translation
  tasks/react-performance-debugging
  tasks/shock-analysis-demand
  tasks/threejs-to-obj
  tasks/virtualhome-agent-planning
  tasks/weighted-gdp-calc
)

TASKS_CSV="$(IFS=,; echo "${TASK_PATHS[*]}")"

NOISE_FILTER='Failed to fetch remote model cost map|Failed to retrieve model info for '\''anthropic/MiniMax-M2.7'\''|Provider List: https://docs.litellm.ai/docs/providers'
nohup bash -lc '
  ./scripts/experiments/rq1.sh "'"${MINIMAX_MODEL:-anthropic/MiniMax-M2.5}"'" \
    --backend skillsbench \
    --max-parallel-tasks 2 \
    --skillsbench-task-path "'"${TASKS_CSV}"'" \
    2>&1 | grep -vE "'"${NOISE_FILTER}"'"
' > retry_error3.log 2>&1 &
