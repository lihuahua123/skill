#!/usr/bin/env bash

set -euo pipefail

PATTERN='harbor run|scripts/benchmark.py|scripts/run.sh|run_with_gateway.sh|openclaw gateway run|scripts/experiments/rq1.sh|scripts/experiments/rq4.sh|scripts/experiments/retry_error.sh'

echo "Benchmark-related processes before stop:"
ps -ef | rg "${PATTERN}" || true

pkill -f "harbor run" || true
pkill -f "scripts/benchmark.py" || true
pkill -f "scripts/run_with_gateway.sh" || true
pkill -f "openclaw gateway run" || true
pkill -f "scripts/experiments/rq1.sh" || true
pkill -f "scripts/experiments/rq4.sh" || true
pkill -f "scripts/experiments/retry_error.sh" || true

sleep 1

echo
echo "Benchmark-related processes after stop:"
ps -ef | rg "${PATTERN}" || true
