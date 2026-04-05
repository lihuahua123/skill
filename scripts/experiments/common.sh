#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

resolve_model() {
  if [[ $# -ge 1 && -n "${1}" ]]; then
    printf '%s\n' "$1"
    return 0
  fi
  if [[ -n "${MODEL:-}" ]]; then
    printf '%s\n' "${MODEL}"
    return 0
  fi
  echo "Usage: $0 MODEL [extra benchmark args...]" >&2
  echo "Or set MODEL in the environment." >&2
  exit 2
}

option_supplied() {
  local option="$1"
  shift
  local arg
  for arg in "$@"; do
    if [[ "${arg}" == "${option}" || "${arg}" == "${option}="* ]]; then
      return 0
    fi
  done
  return 1
}

default_suite() {
  printf '%s\n' "${SUITE:-all}"
}

default_runs() {
  printf '%s\n' "${RUNS:-1}"
}

extract_option_value() {
  local option="$1"
  shift
  local arg
  local next_is_value=0
  for arg in "$@"; do
    if [[ ${next_is_value} -eq 1 ]]; then
      printf '%s\n' "${arg}"
      return 0
    fi
    if [[ "${arg}" == "${option}" ]]; then
      next_is_value=1
      continue
    fi
    if [[ "${arg}" == "${option}="* ]]; then
      printf '%s\n' "${arg#${option}=}"
      return 0
    fi
  done
  return 1
}

extract_option_values() {
  local option="$1"
  shift
  local arg
  local next_is_value=0
  local found=1
  for arg in "$@"; do
    if [[ ${next_is_value} -eq 1 ]]; then
      printf '%s\0' "${arg}"
      next_is_value=0
      found=0
      continue
    fi
    if [[ "${arg}" == "${option}" ]]; then
      next_is_value=1
      continue
    fi
    if [[ "${arg}" == "${option}="* ]]; then
      printf '%s\0' "${arg#${option}=}"
      found=0
    fi
  done
  return "${found}"
}

selected_backend() {
  local backend
  if backend="$(extract_option_value --backend "$@")"; then
    printf '%s\n' "${backend}"
    return 0
  fi
  printf '%s\n' "${BENCHMARK_BACKEND:-pinchbench}"
}

append_if_present() {
  local -n target_ref="$1"
  local option="$2"
  shift 2
  local value
  if value="$(extract_option_value "${option}" "$@")"; then
    target_ref+=("${option}" "${value}")
  fi
}

filter_out_option() {
  local option="$1"
  shift
  local filtered=()
  local skip_next=0
  local arg
  for arg in "$@"; do
    if [[ ${skip_next} -eq 1 ]]; then
      skip_next=0
      continue
    fi
    if [[ "${arg}" == "${option}" ]]; then
      skip_next=1
      continue
    fi
    if [[ "${arg}" == "${option}="* ]]; then
      continue
    fi
    filtered+=("${arg}")
  done
  printf '%s\0' "${filtered[@]}"
}

run_benchmark() {
  local output_dir="$1"
  shift
  local backend
  backend="$(selected_backend "$@")"
  case "${backend}" in
    pinchbench)
      if option_supplied --skillsbench-task-path "$@"; then
        echo "--skillsbench-task-path does not match backend=pinchbench" >&2
        exit 2
      fi
      local forwarded_args=()
      mapfile -d '' -t forwarded_args < <(filter_out_option --backend "$@")
      (
        cd "${REPO_ROOT}"
        ./scripts/run.sh "${forwarded_args[@]}" --output-dir "${output_dir}" --no-upload
      )
      ;;
    skillsbench)
      if option_supplied --pinchbench-task-id "$@"; then
        echo "--pinchbench-task-id does not match backend=skillsbench" >&2
        exit 2
      fi
      local model_name=""
      local skillsbench_task_paths=()
      if model_name="$(extract_option_value --model "$@")"; then
        :
      else
        echo "Missing --model for backend=skillsbench" >&2
        exit 2
      fi
      if extract_option_values --skillsbench-task-path "$@" >/dev/null; then
        mapfile -d '' -t skillsbench_task_paths < <(extract_option_values --skillsbench-task-path "$@")
      else
        skillsbench_task_paths=()
      fi
      local model_slug
      model_slug="$(printf '%s' "${model_name}" | tr '/.' '--')"
      local aggregate_output="${REPO_ROOT}/${output_dir}/skillsbench__${model_slug}.json"
      local cmd=(
        env
        -u HTTP_PROXY
        -u HTTPS_PROXY
        -u http_proxy
        -u https_proxy
        -u ALL_PROXY
        -u all_proxy
        -u SOCKS_PROXY
        -u socks_proxy
        uv run python scripts/run_skillsbench_experiment.py
        --backend skillsbench
        --model "${model_name}"
        --aggregate-output "${aggregate_output}"
      )
      if [[ "${SKILLSBENCH_APPEND_OUTPUT:-0}" == "1" ]]; then
        cmd+=(
          --append-aggregate-output
        )
      fi
      local skillsbench_task_path
      for skillsbench_task_path in "${skillsbench_task_paths[@]}"; do
        cmd+=(
          --skillsbench-task-path "${skillsbench_task_path}"
        )
      done
      append_if_present cmd --agent-name "$@"
      append_if_present cmd --job-name "$@"
      append_if_present cmd --jobs-root "$@"
      append_if_present cmd --benchmark-version "$@"
      append_if_present cmd --run-id "$@"
      append_if_present cmd --max-task-attempts "$@"
      append_if_present cmd --feedback-policy "$@"
      append_if_present cmd --feedback-format "$@"
      append_if_present cmd --feedback-strategy "$@"
      append_if_present cmd --stop-rule "$@"
      append_if_present cmd --stop-threshold "$@"
      append_if_present cmd --api-base "$@"
      append_if_present cmd --api-key "$@"
      (
        cd /hy-tmp/skillsbench
        "${cmd[@]}"
      )
      ;;
    *)
      echo "Unsupported backend: ${backend}" >&2
      exit 2
      ;;
  esac
}

latest_result_json() {
  local results_dir="$1"
  find "${REPO_ROOT}/${results_dir}" -maxdepth 1 -name '*.json' | sort | tail -n 1
}

result_has_perfect_success() {
  local result_json="$1"
  python3 - "$result_json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

success_rate = float((payload.get("efficiency") or {}).get("success_rate", 0.0) or 0.0)
sys.exit(0 if success_rate >= 1.0 else 1)
PY
}

run_analysis() {
  local results_dir="$1"
  local analysis_dir="$2"
  local label_mode="${3:-policy}"
  (
    cd "${REPO_ROOT}"
    mapfile -t json_files < <(find "${results_dir}" -maxdepth 1 -name '*.json' | sort)
    if [[ ${#json_files[@]} -eq 0 ]]; then
      echo "No result JSON files found in ${results_dir}" >&2
      exit 1
    fi
    python3 scripts/analyze_retries.py "${json_files[@]}" \
      --output-dir "${analysis_dir}" \
      --label-mode "${label_mode}"
  )
}
