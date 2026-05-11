#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

INSTANCE_ID="${INSTANCE_ID:-astropy__astropy-13033}"
DATASET_PATH="${DATASET_PATH:-${REPO_ROOT}/data/swebench_verified/test-00000-of-00001.parquet}"
DATASET_SPLIT="${DATASET_SPLIT:-test}"
EVAL_DATASET_NAME="${EVAL_DATASET_NAME:-princeton-nlp/SWE-Bench_Verified}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_ID="${RUN_ID:-real-swebench-eval-${INSTANCE_ID}-${TIMESTAMP}}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${REPO_ROOT}/swebench/log/${RUN_ID}}"
RUNNER_PYTHON="${RUNNER_PYTHON:-${REPO_ROOT}/../skillsbench/.venv/bin/python}"
MAX_TASK_ATTEMPTS="${MAX_TASK_ATTEMPTS:-6}"
MODEL="${MODEL:-anthropic/MiniMax-M2.7}"
SWEBENCH_AGENT_BACKEND="${SWEBENCH_AGENT_BACKEND:-plain-mini}"
STOP_CHECK_EARLY_STOP_ENABLED="${STOP_CHECK_EARLY_STOP_ENABLED:-false}"
STOP_CHECK_ZERO_PROGRESS_STREAK="${STOP_CHECK_ZERO_PROGRESS_STREAK:-2}"
STOP_CHECK_YES_STREAK="${STOP_CHECK_YES_STREAK:-2}"
SKILLSBENCH_SKILL_GUIDANCE="${SKILLSBENCH_SKILL_GUIDANCE:-false}"
INJECT_TOKEN_EFFICIENT_TRIAGE_FIRST_PROMPT="${INJECT_TOKEN_EFFICIENT_TRIAGE_FIRST_PROMPT:-true}"
RETRY_WORKSPACE_STRATEGY="${RETRY_WORKSPACE_STRATEGY:-fresh}" #preserve

if [[ ! -x "${RUNNER_PYTHON}" ]]; then
  echo "Runner python is not executable: ${RUNNER_PYTHON}" >&2
  exit 2
fi

if (( MAX_TASK_ATTEMPTS <= 0 )); then
  echo "MAX_TASK_ATTEMPTS must be a positive integer. Got: ${MAX_TASK_ATTEMPTS}" >&2
  exit 2
fi

configure_minimax_anthropic_env() {
  local model_id="${1:-}"
  case "${model_id}" in
    anthropic/MiniMax-*)
      ;;
    *)
      return 0
      ;;
  esac

  local key_file="${MINIMAX_API_KEY_FILE:-/data/lirui/skill_study/.minimaxapikey}"
  local anthropic_api_key="${ANTHROPIC_API_KEY:-}"
  if [[ -z "${anthropic_api_key}" || "${anthropic_api_key}" == dummy-* ]]; then
    if [[ ! -f "${key_file}" ]]; then
      echo "Missing MiniMax API key file: ${key_file}" >&2
      echo "Set ANTHROPIC_API_KEY or MINIMAX_API_KEY_FILE before running ${model_id}." >&2
      exit 2
    fi
    export ANTHROPIC_API_KEY
    ANTHROPIC_API_KEY="$(tr -d '\r\n' < "${key_file}")"
  fi

  export ANTHROPIC_BASE_URL="${MINIMAX_ANTHROPIC_BASE_URL:-https://api.minimaxi.com/anthropic}"
}

configure_minimax_anthropic_env "${MODEL}"

HF_HOME=/tmp/hf_cache "${RUNNER_PYTHON}" "${REPO_ROOT}/scripts/run_swebench_with_minisweagent.py" \
  --model "${MODEL}" \
  --dataset-path "${DATASET_PATH}" \
  --dataset-split "${DATASET_SPLIT}" \
  --eval-dataset-name "${EVAL_DATASET_NAME}" \
  --run-id "${RUN_ID}" \
  --output-root "${OUTPUT_ROOT}" \
  --swebench-instance-id "${INSTANCE_ID}" \
  --max-task-attempts "${MAX_TASK_ATTEMPTS}" \
  --swebench-agent-backend "${SWEBENCH_AGENT_BACKEND}" \
  --swebench-max-workers 1 \
  --stop-check-early-stop-enabled "${STOP_CHECK_EARLY_STOP_ENABLED}" \
  --stop-check-zero-progress-streak "${STOP_CHECK_ZERO_PROGRESS_STREAK}" \
  --stop-check-yes-streak "${STOP_CHECK_YES_STREAK}" \
  --skillsbench-skill-guidance "${SKILLSBENCH_SKILL_GUIDANCE}" \
  --inject-token-efficient-triage-first-prompt "${INJECT_TOKEN_EFFICIENT_TRIAGE_FIRST_PROMPT}" \
  --retry-workspace-strategy "${RETRY_WORKSPACE_STRATEGY}" \
  --runner-python "${RUNNER_PYTHON}"

echo "run_id=${RUN_ID}"
echo "output_root=${OUTPUT_ROOT}"
echo "task_summary=${OUTPUT_ROOT}/${INSTANCE_ID}/task_summary.json"
