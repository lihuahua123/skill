#!/usr/bin/env bash

set -euo pipefail

KEEP_UNTIL="${DOCKER_GC_KEEP_UNTIL:-168h}"
PRUNE_IMAGES=0
PRUNE_CONTAINERS=0
PRUNE_NETWORKS=0
PRUNE_VOLUMES=0
QUIET=0

usage() {
  cat <<'EOF'
Usage: docker_gc.sh [options]

Safely prune Docker build cache first, then optionally prune other unused objects.

Options:
  --until DURATION   Prune objects older than this age. Default: 168h
  --images           Also prune unused images older than --until
  --containers       Also prune stopped containers
  --networks         Also prune unused networks
  --volumes          Also prune unused volumes
  --all              Equivalent to --images --containers --networks
  --aggressive       Equivalent to --all --volumes
  --quiet            Skip before/after docker system df
  -h, --help         Show this help

Examples:
  ./skill/scripts/docker_gc.sh
  ./skill/scripts/docker_gc.sh --until 72h --images
  ./skill/scripts/docker_gc.sh --aggressive
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --until)
      KEEP_UNTIL="${2:-}"
      shift 2
      ;;
    --images)
      PRUNE_IMAGES=1
      shift
      ;;
    --containers)
      PRUNE_CONTAINERS=1
      shift
      ;;
    --networks)
      PRUNE_NETWORKS=1
      shift
      ;;
    --volumes)
      PRUNE_VOLUMES=1
      shift
      ;;
    --all)
      PRUNE_IMAGES=1
      PRUNE_CONTAINERS=1
      PRUNE_NETWORKS=1
      shift
      ;;
    --aggressive)
      PRUNE_IMAGES=1
      PRUNE_CONTAINERS=1
      PRUNE_NETWORKS=1
      PRUNE_VOLUMES=1
      shift
      ;;
    --quiet)
      QUIET=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${KEEP_UNTIL}" ]]; then
  echo "--until cannot be empty" >&2
  exit 2
fi

if [[ "${QUIET}" -eq 0 ]]; then
  echo "[before] docker system df"
  docker system df
fi

echo "[prune] docker builder prune --all --force --filter until=${KEEP_UNTIL}"
docker builder prune --all --force --filter "until=${KEEP_UNTIL}"

if [[ "${PRUNE_IMAGES}" -eq 1 ]]; then
  echo "[prune] docker image prune --all --force --filter until=${KEEP_UNTIL}"
  docker image prune --all --force --filter "until=${KEEP_UNTIL}"
fi

if [[ "${PRUNE_CONTAINERS}" -eq 1 ]]; then
  echo "[prune] docker container prune --force"
  docker container prune --force
fi

if [[ "${PRUNE_NETWORKS}" -eq 1 ]]; then
  echo "[prune] docker network prune --force"
  docker network prune --force
fi

if [[ "${PRUNE_VOLUMES}" -eq 1 ]]; then
  echo "[prune] docker volume prune --force"
  docker volume prune --force
fi

if [[ "${QUIET}" -eq 0 ]]; then
  echo "[after] docker system df"
  docker system df
fi
