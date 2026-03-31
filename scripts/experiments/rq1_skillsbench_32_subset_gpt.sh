#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTODL_KEY_FILE="/root/autodlAPIKEY"

MODEL="${1:-openai/gpt-5.3-codex}"
if [[ $# -gt 0 ]]; then
  shift
fi

OPENAI_KEY="${OPENAI_API_KEY:-${OPENAI_KEY:-}}"
if [[ -z "${OPENAI_KEY}" && -f "${AUTODL_KEY_FILE}" ]]; then
  OPENAI_KEY="$(tr -d '\r\n' < "${AUTODL_KEY_FILE}")"
fi
OPENAI_BASE="${OPENAI_API_BASE:-${OPENAI_BASE_URL:-https://www.autodl.art/api/v1}}"

if [[ -z "${OPENAI_KEY}" ]]; then
  echo "Missing GPT API key. Set OPENAI_API_KEY/OPENAI_KEY or create ${AUTODL_KEY_FILE}." >&2
  exit 2
fi

EXTRA_ARGS=("$@")
if ! printf '%s\0' "${EXTRA_ARGS[@]}" | grep -zq -- '--api-key'; then
  EXTRA_ARGS=(--api-key "${OPENAI_KEY}" "${EXTRA_ARGS[@]}")
fi
if [[ -n "${OPENAI_BASE}" ]] && ! printf '%s\0' "${EXTRA_ARGS[@]}" | grep -zq -- '--api-base'; then
  EXTRA_ARGS=(--api-base "${OPENAI_BASE}" "${EXTRA_ARGS[@]}")
fi

exec "${SCRIPT_DIR}/rq1_skillsbench_32_subset.sh" "${MODEL}" "${EXTRA_ARGS[@]}"
