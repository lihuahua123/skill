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

default_suite() {
  printf '%s\n' "${SUITE:-all}"
}

default_runs() {
  printf '%s\n' "${RUNS:-1}"
}

run_benchmark() {
  local output_dir="$1"
  shift
  (
    cd "${REPO_ROOT}"
    ./scripts/run.sh "$@" --output-dir "${output_dir}" --no-upload
  )
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
