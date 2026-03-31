#!/usr/bin/env bash

set -euo pipefail

# Ensure uv is on PATH (e.g. when installed via astral.sh to ~/.local/bin)
export PATH="${HOME}/.local/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

GATEWAY_HOST="${PINCHBENCH_GATEWAY_HOST:-127.0.0.1}"
GATEWAY_PORT="${PINCHBENCH_GATEWAY_PORT:-8080}"
GATEWAY_BIND="${PINCHBENCH_GATEWAY_BIND:-loopback}"
GATEWAY_LOG_DIR="${PINCHBENCH_GATEWAY_LOG_DIR:-/tmp/openclaw}"
GATEWAY_LOG_FILE="${GATEWAY_LOG_DIR}/pinchbench-gateway-${GATEWAY_PORT}.log"

gateway_pid=""
started_gateway=0

cleanup() {
  if [[ "${started_gateway}" -eq 1 && -n "${gateway_pid}" ]]; then
    kill "${gateway_pid}" 2>/dev/null || true
    wait "${gateway_pid}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

is_gateway_listening() {
  ss -ltn "sport = :${GATEWAY_PORT}" | tail -n +2 | grep -q ":${GATEWAY_PORT}[[:space:]]"
}

wait_for_gateway() {
  local attempts=30
  local i
  for ((i = 1; i <= attempts; i++)); do
    if is_gateway_listening; then
      return 0
    fi
    sleep 1
  done
  return 1
}

mkdir -p "${GATEWAY_LOG_DIR}"

if is_gateway_listening; then
  echo "Reusing existing gateway on ${GATEWAY_HOST}:${GATEWAY_PORT}" >&2
else
  echo "Starting gateway on ${GATEWAY_HOST}:${GATEWAY_PORT}" >&2
  (
    cd "${REPO_ROOT}"
    exec openclaw gateway run --bind "${GATEWAY_BIND}" --port "${GATEWAY_PORT}"
  ) >"${GATEWAY_LOG_FILE}" 2>&1 &
  gateway_pid="$!"
  started_gateway=1

  if ! wait_for_gateway; then
    echo "Gateway did not become ready on port ${GATEWAY_PORT}. Log: ${GATEWAY_LOG_FILE}" >&2
    exit 1
  fi
fi

cd "${REPO_ROOT}"
exec uv run scripts/benchmark.py "$@"
