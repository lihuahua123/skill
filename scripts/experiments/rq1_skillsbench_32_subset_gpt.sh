#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTODL_KEY_FILE="/hy-tmp/.autodlapikey"
AUTODL_BASE_DEFAULT="https://www.autodl.art/api/v1"

MODEL="${1:-autodl/gpt-5.3-codex}"
if [[ $# -gt 0 ]]; then
  shift
fi

AUTODL_KEY="${AUTODL_API_KEY:-${OPENAI_API_KEY:-${OPENAI_KEY:-}}}"
if [[ -z "${AUTODL_KEY}" && -f "${AUTODL_KEY_FILE}" ]]; then
  AUTODL_KEY="$(tr -d '\r\n' < "${AUTODL_KEY_FILE}")"
fi
AUTODL_BASE="${AUTODL_API_BASE:-${AUTODL_BASE_URL:-${OPENAI_API_BASE:-${OPENAI_BASE_URL:-${AUTODL_BASE_DEFAULT}}}}}"

if [[ -z "${AUTODL_KEY}" ]]; then
  echo "Missing Autodl API key. Set AUTODL_API_KEY or create ${AUTODL_KEY_FILE}." >&2
  exit 2
fi

EXTRA_ARGS=("$@")
if ! printf '%s\0' "${EXTRA_ARGS[@]}" | grep -zq -- '--api-key'; then
  EXTRA_ARGS=(--api-key "${AUTODL_KEY}" "${EXTRA_ARGS[@]}")
fi
if [[ -n "${AUTODL_BASE}" ]] && ! printf '%s\0' "${EXTRA_ARGS[@]}" | grep -zq -- '--api-base'; then
  EXTRA_ARGS=(--api-base "${AUTODL_BASE}" "${EXTRA_ARGS[@]}")
fi

exec "${SCRIPT_DIR}/rq1_skillsbench_32_subset.sh" "${MODEL}" \
  --feedback-answer-safety no-answers \
  "${EXTRA_ARGS[@]}"
