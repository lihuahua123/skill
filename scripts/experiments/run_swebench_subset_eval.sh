#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DATASET_PATH="${DATASET_PATH:-${REPO_ROOT}/data/swebench_verified/test-00000-of-00001.parquet}"
DATASET_SPLIT="${DATASET_SPLIT:-test}"
EVAL_DATASET_NAME="${EVAL_DATASET_NAME:-princeton-nlp/SWE-Bench_Verified}"
RUNNER_PYTHON="${RUNNER_PYTHON:-${REPO_ROOT}/../skillsbench/.venv/bin/python}"
SUBSET_SEED="${SUBSET_SEED:-251016786}"
MAX_TASK_ATTEMPTS="${MAX_TASK_ATTEMPTS:-6}"
MODEL="${MODEL:-anthropic/MiniMax-M2.5}"
SWEBENCH_AGENT_BACKEND="${SWEBENCH_AGENT_BACKEND:-plain-mini}"
MAX_PARALLEL="${MAX_PARALLEL:-1}"
BATCH_SIZE="${BATCH_SIZE:-10}"
DOCKER_PRUNE_BETWEEN_BATCHES="${DOCKER_PRUNE_BETWEEN_BATCHES:-1}"
DOCKER_PRUNE_AFTER_FINAL_BATCH="${DOCKER_PRUNE_AFTER_FINAL_BATCH:-0}"
RUN_STAMP="${RUN_STAMP:-$(date +"%Y-%m-%d__%H-%M-%S")}"
RUN_ID="${RUN_ID:-real-swebench-subset-100-${RUN_STAMP}}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${REPO_ROOT}/swebench/log/${RUN_ID}}"
MANIFEST_PATH="${MANIFEST_PATH:-${OUTPUT_ROOT}/subset_instance_ids.txt}"
SUMMARY_PATH="${SUMMARY_PATH:-${OUTPUT_ROOT}/subset_summary.json}"
TASK_LOG_DIR="${TASK_LOG_DIR:-${OUTPUT_ROOT}/task_logs}"

if [[ ! -x "${RUNNER_PYTHON}" ]]; then
  echo "Runner python is not executable: ${RUNNER_PYTHON}" >&2
  exit 2
fi

if (( MAX_PARALLEL <= 0 )); then
  echo "MAX_PARALLEL must be a positive integer. Got: ${MAX_PARALLEL}" >&2
  exit 2
fi

if (( BATCH_SIZE <= 0 )); then
  echo "BATCH_SIZE must be a positive integer. Got: ${BATCH_SIZE}" >&2
  exit 2
fi

if (( MAX_TASK_ATTEMPTS <= 0 )); then
  echo "MAX_TASK_ATTEMPTS must be a positive integer. Got: ${MAX_TASK_ATTEMPTS}" >&2
  exit 2
fi

mkdir -p "${OUTPUT_ROOT}" "${TASK_LOG_DIR}"

HF_HOME=/tmp/hf_cache XDG_CACHE_HOME=/tmp/xdg_cache "${RUNNER_PYTHON}" \
  "${REPO_ROOT}/scripts/select_swebench_verified_subset.py" \
  --dataset-path "${DATASET_PATH}" \
  --dataset-split "${DATASET_SPLIT}" \
  --seed "${SUBSET_SEED}" \
  --output "${MANIFEST_PATH}" \
  --summary-output "${SUMMARY_PATH}"

mapfile -t INSTANCE_IDS < <(sed '/^[[:space:]]*$/d' "${MANIFEST_PATH}")

if [[ "${#INSTANCE_IDS[@]}" -eq 0 ]]; then
  echo "No instance ids were selected. Manifest: ${MANIFEST_PATH}" >&2
  exit 3
fi

run_instance() {
  local instance_id="$1"
  local task_log="${TASK_LOG_DIR}/${instance_id}.log"
  local task_summary="${OUTPUT_ROOT}/${instance_id}/task_summary.json"

  if [[ -f "${task_summary}" ]]; then
    {
      echo "[$(date +"%F %T")] SKIP ${instance_id}"
      echo "reason=existing_task_summary"
      echo "task_summary=${task_summary}"
    } >"${task_log}"
    return 0
  fi

  {
    echo "[$(date +"%F %T")] START ${instance_id}"
    INSTANCE_ID="${instance_id}" \
    DATASET_PATH="${DATASET_PATH}" \
    DATASET_SPLIT="${DATASET_SPLIT}" \
    EVAL_DATASET_NAME="${EVAL_DATASET_NAME}" \
    RUN_ID="${RUN_ID}-${instance_id}" \
    OUTPUT_ROOT="${OUTPUT_ROOT}" \
    MAX_TASK_ATTEMPTS="${MAX_TASK_ATTEMPTS}" \
    MODEL="${MODEL}" \
    SWEBENCH_AGENT_BACKEND="${SWEBENCH_AGENT_BACKEND}" \
    RUNNER_PYTHON="${RUNNER_PYTHON}" \
    "${SCRIPT_DIR}/run_swebench_single_eval.sh"
    echo "[$(date +"%F %T")] DONE ${instance_id}"
  } >"${task_log}" 2>&1
}

run_batch() {
  local active_jobs=0
  local instance_id
  for instance_id in "$@"; do
    run_instance "${instance_id}" &
    ((active_jobs += 1))
    if (( active_jobs >= MAX_PARALLEL )); then
      wait -n || true
      active_jobs=$((active_jobs - 1))
    fi
  done

  while (( active_jobs > 0 )); do
    wait -n || true
    active_jobs=$((active_jobs - 1))
  done
}

cleanup_docker_artifacts() {
  local batch_number="$1"
  local total_batches="$2"

  if [[ "${DOCKER_PRUNE_BETWEEN_BATCHES}" != "1" ]]; then
    return 0
  fi

  if ! command -v docker >/dev/null 2>&1; then
    echo "[$(date +"%F %T")] WARN batch=${batch_number}/${total_batches} docker not found; skip prune" >&2
    return 0
  fi

  echo "[$(date +"%F %T")] CLEANUP batch=${batch_number}/${total_batches} docker builder prune -af"
  docker builder prune -af || echo "[$(date +"%F %T")] WARN docker builder prune failed" >&2

  echo "[$(date +"%F %T")] CLEANUP batch=${batch_number}/${total_batches} docker image prune -af"
  docker image prune -af || echo "[$(date +"%F %T")] WARN docker image prune failed" >&2
}

total_instances="${#INSTANCE_IDS[@]}"
total_batches="$(((total_instances + BATCH_SIZE - 1) / BATCH_SIZE))"
batch_number=0

for ((batch_start = 0; batch_start < total_instances; batch_start += BATCH_SIZE)); do
  batch_number=$((batch_number + 1))
  batch_ids=("${INSTANCE_IDS[@]:batch_start:BATCH_SIZE}")
  batch_end=$((batch_start + ${#batch_ids[@]}))

  echo "[$(date +"%F %T")] BATCH_START ${batch_number}/${total_batches} instances=${#batch_ids[@]} range=$((batch_start + 1))-${batch_end}"
  run_batch "${batch_ids[@]}"
  echo "[$(date +"%F %T")] BATCH_DONE ${batch_number}/${total_batches}"

  if (( batch_number < total_batches )) || [[ "${DOCKER_PRUNE_AFTER_FINAL_BATCH}" == "1" ]]; then
    cleanup_docker_artifacts "${batch_number}" "${total_batches}"
  fi
done

HF_HOME=/tmp/hf_cache XDG_CACHE_HOME=/tmp/xdg_cache "${RUNNER_PYTHON}" - <<'PY' \
  "${MANIFEST_PATH}" \
  "${OUTPUT_ROOT}" \
  "${SUMMARY_PATH}" \
  "${MAX_TASK_ATTEMPTS}"
from __future__ import annotations

import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
output_root = Path(sys.argv[2])
summary_path = Path(sys.argv[3])
max_task_attempts = int(sys.argv[4])

instance_ids = [line.strip() for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
completed = 0
resolved = 0
failed = 0
missing = []
for instance_id in instance_ids:
    task_summary_path = output_root / instance_id / "task_summary.json"
    if not task_summary_path.exists():
        missing.append(instance_id)
        continue
    completed += 1
    payload = json.loads(task_summary_path.read_text(encoding="utf-8"))
    if bool(payload.get("success_within_budget")):
        resolved += 1
    else:
        failed += 1

summary = {}
if summary_path.exists():
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
summary.update(
    {
        "manifest_path": str(manifest_path),
        "output_root": str(output_root),
        "max_task_attempts": max_task_attempts,
        "task_count": len(instance_ids),
        "completed_count": completed,
        "resolved_count": resolved,
        "failed_count": failed,
        "missing_count": len(missing),
        "missing_instance_ids": missing,
    }
)
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(f"task_count={len(instance_ids)}")
print(f"completed_count={completed}")
print(f"resolved_count={resolved}")
print(f"failed_count={failed}")
print(f"missing_count={len(missing)}")
print(f"manifest_path={manifest_path}")
print(f"summary_path={summary_path}")
print(f"output_root={output_root}")
PY
