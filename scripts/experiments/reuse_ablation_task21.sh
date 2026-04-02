#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

MODEL="${1:-${MODEL:-autodl/Kimi-K2.5}}"
BASELINE_DIR="${REUSE_ABLATION_BASELINE_DIR:-results/reuse_ablation/task21_baseline}"
REUSE_DIR="${REUSE_ABLATION_REUSE_DIR:-results/reuse_ablation/task21_reuse}"
MAX_ATTEMPTS="${REUSE_ABLATION_MAX_ATTEMPTS:-1}"

cd "${REPO_ROOT}"

./scripts/run.sh \
  --model "${MODEL}" \
  --suite task_21_openclaw_comprehension \
  --runs 1 \
  --max-task-attempts "${MAX_ATTEMPTS}" \
  --output-dir "${BASELINE_DIR}" \
  --no-upload

./scripts/run.sh \
  --model "${MODEL}" \
  --suite task_21_openclaw_comprehension_reuse \
  --runs 1 \
  --max-task-attempts "${MAX_ATTEMPTS}" \
  --output-dir "${REUSE_DIR}" \
  --no-upload

BASELINE_JSON="$(find "${BASELINE_DIR}" -maxdepth 1 -name '*.json' | sort | tail -n 1)"
REUSE_JSON="$(find "${REUSE_DIR}" -maxdepth 1 -name '*.json' | sort | tail -n 1)"

python3 scripts/compare_reuse_ablation.py \
  --baseline "${BASELINE_JSON}" \
  --reuse "${REUSE_JSON}" \
  --pretty
