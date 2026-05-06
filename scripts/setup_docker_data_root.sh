#!/usr/bin/env bash

set -euo pipefail

TARGET_ROOT="${1:-/data/docker}"
DAEMON_JSON_PATH="${DAEMON_JSON_PATH:-/etc/docker/daemon.json}"

usage() {
  cat <<EOF
Usage: setup_docker_data_root.sh [TARGET_ROOT]

Prepare a Docker daemon.json snippet that moves Docker's data-root under TARGET_ROOT.
Default TARGET_ROOT: /data/docker

Examples:
  ./skill/scripts/setup_docker_data_root.sh
  ./skill/scripts/setup_docker_data_root.sh /data/docker

Suggested apply steps:
  1. sudo mkdir -p ${TARGET_ROOT}
  2. sudo cp ${DAEMON_JSON_PATH} ${DAEMON_JSON_PATH}.bak  # if it exists
  3. Merge the JSON shown by this script into ${DAEMON_JSON_PATH}
  4. sudo systemctl stop docker
  5. sudo rsync -aP /var/lib/docker/ ${TARGET_ROOT}/
  6. sudo systemctl start docker
  7. docker info | grep 'Docker Root Dir'
EOF
}

if [[ "${TARGET_ROOT}" == "-h" || "${TARGET_ROOT}" == "--help" ]]; then
  usage
  exit 0
fi

cat <<EOF
{
  "data-root": "${TARGET_ROOT}"
}
EOF
