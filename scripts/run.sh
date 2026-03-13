#!/usr/bin/env bash
# Convenience wrapper for running PinchBench
# Usage: ./scripts/run.sh --model anthropic/claude-sonnet-4

set -e
# Ensure uv is on PATH (e.g. when installed via astral.sh to ~/.local/bin)
export PATH="${HOME}/.local/bin:${PATH}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
exec uv run scripts/benchmark.py "$@"
