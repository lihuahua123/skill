#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"
TASK_PATHS=(
  # Retry tasks after verifier/env fixes from skillsbench__anthropic-MiniMax-M2-5__2026-04-15__16-39-03
  tasks/financial-modeling-qa
  tasks/fix-build-agentops
  tasks/fix-druid-loophole-cve
  tasks/organize-messy-files
  tasks/pptx-reference-formatting
  tasks/seismic-phase-picking
  tasks/shock-analysis-supply
  tasks/xlsx-recover-data
  tasks/fix-erlang-ssh-cve
  tasks/lean4-proof
  tasks/setup-fuzzing-py
  tasks/software-dependency-audit
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
