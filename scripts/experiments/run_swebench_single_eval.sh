#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

INSTANCE_ID="${INSTANCE_ID:-astropy__astropy-12907}"
DATASET_PATH="${DATASET_PATH:-${REPO_ROOT}/data/swebench_verified/test-00000-of-00001.parquet}"
DATASET_SPLIT="${DATASET_SPLIT:-test}"
EVAL_DATASET_NAME="${EVAL_DATASET_NAME:-princeton-nlp/SWE-Bench_Verified}"
RUN_ID="${RUN_ID:-real-swebench-eval-${INSTANCE_ID}}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/tmp/${RUN_ID}}"
RUNNER_PYTHON="${RUNNER_PYTHON:-${REPO_ROOT}/../skillsbench/.venv/bin/python}"

if [[ ! -x "${RUNNER_PYTHON}" ]]; then
  echo "Runner python is not executable: ${RUNNER_PYTHON}" >&2
  exit 2
fi

PATCH_TEXT="$(
  HF_HOME=/tmp/hf_cache "${RUNNER_PYTHON}" - <<'PY' "${DATASET_PATH}" "${INSTANCE_ID}"
from datasets import load_dataset
from pathlib import Path
import sys

dataset_path = Path(sys.argv[1])
instance_id = sys.argv[2]

if dataset_path.suffix == ".parquet":
    dataset = load_dataset("parquet", data_files=str(dataset_path), split="train")
else:
    dataset = load_dataset(str(dataset_path), split="test")

for row in dataset:
    if row["instance_id"] == instance_id:
        patch = row["patch"]
        if not patch:
            raise ValueError(f"Empty patch for instance: {instance_id}")
        print(patch, end="")
        break
else:
    raise ValueError(f"Instance not found in dataset: {instance_id}")
PY
)"

MODEL_OUTPUT_FILE="$(mktemp)"
trap 'rm -f "${MODEL_OUTPUT_FILE}"' EXIT

cat > "${MODEL_OUTPUT_FILE}" <<EOF
THOUGHT: submit patch
\`\`\`bash
cat <<'PATCH' >/tmp/submission.patch
${PATCH_TEXT}
PATCH
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT
cat /tmp/submission.patch
\`\`\`
EOF

HF_HOME=/tmp/hf_cache "${RUNNER_PYTHON}" "${REPO_ROOT}/scripts/run_swebench_with_minisweagent.py" \
  --model deterministic \
  --model-class deterministic \
  --model-output "$(cat "${MODEL_OUTPUT_FILE}")" \
  --dataset-path "${DATASET_PATH}" \
  --dataset-split "${DATASET_SPLIT}" \
  --eval-dataset-name "${EVAL_DATASET_NAME}" \
  --run-id "${RUN_ID}" \
  --output-root "${OUTPUT_ROOT}" \
  --swebench-instance-id "${INSTANCE_ID}" \
  --max-task-attempts 1 \
  --swebench-agent-backend plain-mini \
  --swebench-max-workers 1 \
  --runner-python "${RUNNER_PYTHON}"

echo "run_id=${RUN_ID}"
echo "output_root=${OUTPUT_ROOT}"
echo "eval_result=${OUTPUT_ROOT}/${INSTANCE_ID}/attempt_1/eval_result.json"
