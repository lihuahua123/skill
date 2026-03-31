#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODEL="${1:-}"
if [[ -z "${MODEL}" ]]; then
  echo "Usage: $0 MODEL [extra benchmark args...]" >&2
  exit 2
fi
shift

exec "${SCRIPT_DIR}/rq1.sh" "${MODEL}" \
  --backend skillsbench \
  --skillsbench-task-path tasks/threejs-structure-parser \
  --skillsbench-task-path tasks/python-scala-translation \
  --skillsbench-task-path tasks/fix-build-google-auto \
  --skillsbench-task-path tasks/fix-build-agentops \
  --skillsbench-task-path tasks/court-form-filling \
  --skillsbench-task-path tasks/dialogue-parser \
  --skillsbench-task-path tasks/powerlifting-coef-calc \
  --skillsbench-task-path tasks/earthquake-phase-association \
  --skillsbench-task-path tasks/dapt-intrusion-detection \
  --skillsbench-task-path tasks/setup-fuzzing-py \
  --skillsbench-task-path tasks/software-dependency-audit \
  --skillsbench-task-path tasks/suricata-custom-exfil \
  --skillsbench-task-path tasks/r2r-mpc-control \
  --skillsbench-task-path tasks/energy-market-pricing \
  --skillsbench-task-path tasks/financial-modeling-qa \
  --skillsbench-task-path tasks/find-topk-similiar-chemicals \
  --skillsbench-task-path tasks/react-performance-debugging \
  --skillsbench-task-path tasks/glm-lake-mendota \
  --skillsbench-task-path tasks/lake-warming-attribution \
  --skillsbench-task-path tasks/latex-formula-extraction \
  --skillsbench-task-path tasks/lean4-proof \
  --skillsbench-task-path tasks/manufacturing-equipment-maintenance \
  --skillsbench-task-path tasks/manufacturing-codebook-normalization \
  --skillsbench-task-path tasks/mars-clouds-clustering \
  --skillsbench-task-path tasks/offer-letter-generator \
  --skillsbench-task-path tasks/parallel-tfidf-search \
  --skillsbench-task-path tasks/pedestrian-traffic-counting \
  --skillsbench-task-path tasks/quantum-numerical-simulation \
  --skillsbench-task-path tasks/shock-analysis-demand \
  --skillsbench-task-path tasks/reserves-at-risk-calc \
  --skillsbench-task-path tasks/sec-financial-report \
  --skillsbench-task-path tasks/spring-boot-jakarta-migration \
  --feedback-policy error-localized \
  --feedback-format full-refresh \
  --feedback-strategy original \
  "$@"
