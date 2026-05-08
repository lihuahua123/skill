#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DATASET_PATH="${DATASET_PATH:-${REPO_ROOT}/data/swebench_verified/test-00000-of-00001.parquet}"
DATASET_SPLIT="${DATASET_SPLIT:-test}"
EVAL_DATASET_NAME="${EVAL_DATASET_NAME:-princeton-nlp/SWE-Bench_Verified}"
RUNNER_PYTHON="${RUNNER_PYTHON:-${REPO_ROOT}/../skillsbench/.venv/bin/python}"
SUBSET_SEED="${SUBSET_SEED:-251016786}"
MAX_PARALLEL="${MAX_PARALLEL:-1}"
RUN_STAMP="${RUN_STAMP:-$(date +"%Y-%m-%d__%H-%M-%S")}"
RUN_ID="${RUN_ID:-real-swebench-subset-100-${RUN_STAMP}}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/tmp/${RUN_ID}}"
MANIFEST_PATH="${MANIFEST_PATH:-${OUTPUT_ROOT}/subset_instance_ids.txt}"
SUMMARY_PATH="${SUMMARY_PATH:-${OUTPUT_ROOT}/subset_summary.json}"
TASK_LOG_DIR="${TASK_LOG_DIR:-${OUTPUT_ROOT}/task_logs}"

if [[ ! -x "${RUNNER_PYTHON}" ]]; then
  echo "Runner python is not executable: ${RUNNER_PYTHON}" >&2
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
  local eval_result="${OUTPUT_ROOT}/${instance_id}/attempt_1/eval_result.json"

  if [[ -f "${eval_result}" ]]; then
    {
      echo "[$(date +"%F %T")] SKIP ${instance_id}"
      echo "reason=existing_eval_result"
      echo "eval_result=${eval_result}"
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
    RUNNER_PYTHON="${RUNNER_PYTHON}" \
    "${SCRIPT_DIR}/run_swebench_single_eval.sh"
    echo "[$(date +"%F %T")] DONE ${instance_id}"
  } >"${task_log}" 2>&1
}

active_jobs=0
for instance_id in "${INSTANCE_IDS[@]}"; do
  run_instance "${instance_id}" &
  ((active_jobs += 1))
  if (( active_jobs >= MAX_PARALLEL )); then
    wait -n || true
    ((active_jobs -= 1))
  fi
done

while (( active_jobs > 0 )); do
  wait -n || true
  ((active_jobs -= 1))
done

HF_HOME=/tmp/hf_cache XDG_CACHE_HOME=/tmp/xdg_cache "${RUNNER_PYTHON}" - <<'PY' \
  "${MANIFEST_PATH}" \
  "${OUTPUT_ROOT}" \
  "${SUMMARY_PATH}"
from __future__ import annotations

import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
output_root = Path(sys.argv[2])
summary_path = Path(sys.argv[3])

instance_ids = [line.strip() for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
completed = 0
resolved = 0
failed = 0
missing = []
for instance_id in instance_ids:
    eval_result_path = output_root / instance_id / "attempt_1" / "eval_result.json"
    if not eval_result_path.exists():
        missing.append(instance_id)
        continue
    completed += 1
    payload = json.loads(eval_result_path.read_text(encoding="utf-8"))
    if bool(payload.get("resolved")):
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
