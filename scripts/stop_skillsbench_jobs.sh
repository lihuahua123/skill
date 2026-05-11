#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TARGET_JOB_NAME="${1:-}"
PROCESS_PATTERN='retry_error\.sh|retry_good\.sh|rq1\.sh|rq1_all_tasks\.sh|harbor run|run_skillsbench_with_early_stop|benchmark\.py|docker compose --project-name .*skillsbench/tasks/.*/environment|docker-compose compose --project-name .*skillsbench/tasks/.*/environment'

matches_job_name() {
  local text="${1:-}"
  if [[ -z "${TARGET_JOB_NAME}" ]]; then
    return 0
  fi
  [[ "${text}" == *"${TARGET_JOB_NAME}"* ]]
}

stop_matching_processes() {
  local -a pids=()
  while IFS=$'\t' read -r pid cmd; do
    [[ -n "${pid}" ]] || continue
    if matches_job_name "${cmd}"; then
      pids+=("${pid}")
    fi
  done < <(
    ps -eo pid=,args= | awk '
      /retry_error\.sh|retry_good\.sh|rq1\.sh|rq1_all_tasks\.sh|harbor run|run_skillsbench_with_early_stop|benchmark\.py|docker compose --project-name .*skillsbench\/tasks\/.*\/environment|docker-compose compose --project-name .*skillsbench\/tasks\/.*\/environment/ {
        print $1 "\t" substr($0, index($0, $2))
      }
    '
  )

  if [[ ${#pids[@]} -eq 0 ]]; then
    echo "No matching benchmark processes found."
    return
  fi

  echo "Stopping processes: ${pids[*]}"
  kill "${pids[@]}" 2>/dev/null || true
  sleep 2
  kill -9 "${pids[@]}" 2>/dev/null || true

  # These runners often fork more shells/python children that no longer match
  # the original parent command line. Best-effort: walk the process tree and
  # kill descendants too.
  local pid
  for pid in "${pids[@]}"; do
    pkill -TERM -P "${pid}" 2>/dev/null || true
    pkill -KILL -P "${pid}" 2>/dev/null || true
  done
}

stop_matching_process_groups() {
  local -a group_pids=()
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    group_pids+=("${pid}")
  done < <(pgrep -f "${PROCESS_PATTERN}" || true)

  if [[ ${#group_pids[@]} -eq 0 ]]; then
    return
  fi

  echo "Stopping process groups: ${group_pids[*]}"
  local pid
  for pid in "${group_pids[@]}"; do
    kill -TERM "-${pid}" 2>/dev/null || true
  done
  sleep 2
  for pid in "${group_pids[@]}"; do
    kill -KILL "-${pid}" 2>/dev/null || true
  done
}

collect_compose_projects() {
  {
    docker ps -a --format '{{.Label "com.docker.compose.project"}} {{.Names}}' 2>/dev/null || true
    ps -eo args= | awk '
      /docker compose --project-name .*skillsbench\/tasks\/.*\/environment|docker-compose compose --project-name .*skillsbench\/tasks\/.*\/environment/ {
        for (i = 1; i <= NF; i++) {
          if ($i == "--project-name" && (i + 1) <= NF) {
            print $(i + 1) " process-args"
          }
        }
      }
    '
  } | while read -r project name; do
    [[ -n "${project}" ]] || continue
    if matches_job_name "${project} ${name}"; then
      printf '%s\n' "${project}"
    fi
  done | sort -u
}

stop_compose_projects() {
  mapfile -t projects < <(collect_compose_projects)
  if [[ ${#projects[@]} -eq 0 ]]; then
    echo "No matching docker compose projects found."
    return
  fi

  local project
  for project in "${projects[@]}"; do
    local task_name="${project%%__*}"
    local env_dir="${REPO_ROOT}/../skillsbench/tasks/${task_name}/environment"
    echo "Stopping docker compose project: ${project}"
    if [[ -d "${env_dir}" ]]; then
      docker compose \
        --project-name "${project}" \
        --project-directory "${env_dir}" \
        down --remove-orphans --volumes || true
    else
      mapfile -t container_ids < <(docker ps -aq --filter "label=com.docker.compose.project=${project}")
      if [[ ${#container_ids[@]} -gt 0 ]]; then
        docker rm -f "${container_ids[@]}" || true
      fi
    fi
  done
}

stop_matching_processes
stop_matching_process_groups
stop_compose_projects

echo "Done."
