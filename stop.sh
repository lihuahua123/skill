#!/usr/bin/env bash

set -euo pipefail

PATTERN='run_skillsbench_experiment.py|run_terminus_local_host.py|scripts/benchmark.py|scripts/run.sh|run_with_gateway.sh|openclaw gateway run|scripts/experiments/rq1.sh|scripts/experiments/rq4.sh|scripts/experiments/retry_error.sh'

echo "Benchmark-related processes before stop:"
ps -ef | rg "${PATTERN}" || true

pkill -f "run_skillsbench_experiment.py" || true
pkill -f "run_terminus_local_host.py" || true
pkill -f "scripts/benchmark.py" || true
pkill -f "scripts/run_with_gateway.sh" || true
pkill -f "openclaw gateway run" || true
pkill -f "scripts/experiments/rq1.sh" || true
pkill -f "scripts/experiments/rq4.sh" || true
pkill -f "scripts/experiments/retry_error.sh" || true
pkill -f "uv run python scripts/run_skillsbench_experiment.py" || true

sleep 1

echo
echo "Benchmark-related processes after stop:"
ps -ef | rg "${PATTERN}" || true
