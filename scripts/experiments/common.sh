#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SKILLSBENCH_ROOT_DEFAULT="$(cd "${REPO_ROOT}/.." && pwd)/skillsbench"

resolve_model() {
  if [[ $# -ge 1 && -n "${1}" ]]; then
    printf '%s\n' "$1"
    return 0
  fi
  if [[ -n "${MODEL:-}" ]]; then
    printf '%s\n' "${MODEL}"
    return 0
  fi
  echo "Usage: $0 MODEL [extra benchmark args...]" >&2
  echo "Or set MODEL in the environment." >&2
  exit 2
}

option_supplied() {
  local option="$1"
  shift
  local arg
  for arg in "$@"; do
    if [[ "${arg}" == "${option}" || "${arg}" == "${option}="* ]]; then
      return 0
    fi
  done
  return 1
}

default_suite() {
  printf '%s\n' "${SUITE:-all}"
}

default_runs() {
  printf '%s\n' "${RUNS:-1}"
}

extract_option_value() {
  local option="$1"
  shift
  local arg
  local next_is_value=0
  for arg in "$@"; do
    if [[ ${next_is_value} -eq 1 ]]; then
      printf '%s\n' "${arg}"
      return 0
    fi
    if [[ "${arg}" == "${option}" ]]; then
      next_is_value=1
      continue
    fi
    if [[ "${arg}" == "${option}="* ]]; then
      printf '%s\n' "${arg#${option}=}"
      return 0
    fi
  done
  return 1
}

extract_option_values() {
  local option="$1"
  shift
  local arg
  local next_is_value=0
  local found=1
  for arg in "$@"; do
    if [[ ${next_is_value} -eq 1 ]]; then
      printf '%s\0' "${arg}"
      next_is_value=0
      found=0
      continue
    fi
    if [[ "${arg}" == "${option}" ]]; then
      next_is_value=1
      continue
    fi
    if [[ "${arg}" == "${option}="* ]]; then
      printf '%s\0' "${arg#${option}=}"
      found=0
    fi
  done
  return "${found}"
}

selected_backend() {
  local backend
  if backend="$(extract_option_value --backend "$@")"; then
    printf '%s\n' "${backend}"
    return 0
  fi
  printf '%s\n' "${BENCHMARK_BACKEND:-pinchbench}"
}

skillsbench_root() {
  local root="${SKILLSBENCH_ROOT:-${SKILLSBENCH_ROOT_DEFAULT}}"
  if [[ ! -d "${root}" ]]; then
    echo "SkillsBench root does not exist: ${root}" >&2
    echo "Set SKILLSBENCH_ROOT to your SkillsBench repository path." >&2
    exit 2
  fi
  printf '%s\n' "${root}"
}

skillsbench_mode_from_args() {
  local mode=""
  if mode="$(extract_option_value --mode "$@")"; then
    :
  elif mode="$(extract_option_value --skillsbench-mode "$@")"; then
    :
  else
    mode="${SKILLSBENCH_MODE:-with-skills}"
  fi
  case "${mode}" in
    with-skills)
      printf '%s\n' "${mode}"
      ;;
    without-skills | no-skills)
      printf '%s\n' "without-skills"
      ;;
    *)
      echo "Unsupported SkillsBench mode: ${mode}" >&2
      echo "Supported modes: with-skills, without-skills" >&2
      exit 2
      ;;
  esac
}

skillsbench_tasks_prefix() {
  local mode="${1:-with-skills}"
  case "${mode}" in
    with-skills)
      printf '%s\n' "tasks"
      ;;
    without-skills)
      printf '%s\n' "tasks-no-skills"
      ;;
    *)
      echo "Unsupported SkillsBench mode: ${mode}" >&2
      exit 2
      ;;
  esac
}

skillsbench_tasks_root() {
  local mode="${1:-with-skills}"
  local root
  root="$(skillsbench_root)"
  local prefix
  prefix="$(skillsbench_tasks_prefix "${mode}")"
  printf '%s/%s\n' "${root}" "${prefix}"
}

collect_skillsbench_task_names() {
  local raw_paths=()
  if extract_option_values --skillsbench-task-path "$@" >/dev/null; then
    mapfile -d '' -t raw_paths < <(extract_option_values --skillsbench-task-path "$@")
  fi

  local raw_path
  local segment
  local normalized
  local -A seen=()
  local IFS_OLD="${IFS}"
  for raw_path in "${raw_paths[@]}"; do
    IFS=',' read -r -a segments <<< "${raw_path}"
    for segment in "${segments[@]}"; do
      segment="$(printf '%s' "${segment}" | xargs)"
      [[ -z "${segment}" ]] && continue
      segment="${segment#./}"
      segment="${segment%/}"
      case "${segment}" in
        tasks/*)
          normalized="${segment#tasks/}"
          ;;
        tasks-no-skills/*)
          normalized="${segment#tasks-no-skills/}"
          ;;
        */*)
          normalized="${segment##*/}"
          ;;
        *)
          normalized="${segment}"
          ;;
      esac
      [[ -z "${normalized}" ]] && continue
      if [[ -z "${seen[${normalized}]:-}" ]]; then
        seen["${normalized}"]=1
        printf '%s\0' "${normalized}"
      fi
    done
  done
  IFS="${IFS_OLD}"
}

append_if_present() {
  local -n target_ref="$1"
  local option="$2"
  shift 2
  local value
  if value="$(extract_option_value "${option}" "$@")"; then
    target_ref+=("${option}" "${value}")
  fi
}

filter_out_option() {
  local option="$1"
  shift
  local filtered=()
  local skip_next=0
  local arg
  for arg in "$@"; do
    if [[ ${skip_next} -eq 1 ]]; then
      skip_next=0
      continue
    fi
    if [[ "${arg}" == "${option}" ]]; then
      skip_next=1
      continue
    fi
    if [[ "${arg}" == "${option}="* ]]; then
      continue
    fi
    filtered+=("${arg}")
  done
  printf '%s\0' "${filtered[@]}"
}

run_benchmark() {
  local output_dir="$1"
  shift
  local backend
  backend="$(selected_backend "$@")"
  case "${backend}" in
    pinchbench)
      if option_supplied --skillsbench-task-path "$@" \
        || option_supplied --mode "$@" \
        || option_supplied --skillsbench-mode "$@" \
        || option_supplied --sandbox "$@"; then
        echo "SkillsBench-only options do not match backend=pinchbench" >&2
        exit 2
      fi
      local forwarded_args=()
      mapfile -d '' -t forwarded_args < <(filter_out_option --backend "$@")
      (
        cd "${REPO_ROOT}"
        ./scripts/run.sh "${forwarded_args[@]}" --output-dir "${output_dir}" --no-upload
      )
      ;;
    skillsbench)
      if option_supplied --pinchbench-task-id "$@"; then
        echo "--pinchbench-task-id does not match backend=skillsbench" >&2
        exit 2
      fi
      local model_name
      if model_name="$(extract_option_value --model "$@")"; then
        :
      else
        echo "Missing --model for backend=skillsbench" >&2
        exit 2
      fi

      local mode
      mode="$(skillsbench_mode_from_args "$@")"
      local tasks_root
      tasks_root="$(skillsbench_tasks_root "${mode}")"

      local sandbox
      if sandbox="$(extract_option_value --sandbox "$@")"; then
        :
      else
        sandbox="${SKILLSBENCH_SANDBOX:-docker}"
      fi

      local task_names=()
      if collect_skillsbench_task_names "$@" >/dev/null; then
        mapfile -d '' -t task_names < <(collect_skillsbench_task_names "$@")
      else
        task_names=()
      fi

      local agent_name
      if agent_name="$(extract_option_value --agent-name "$@")"; then
        :
      else
        agent_name="${SKILLSBENCH_AGENT_NAME:-terminus-2}"
      fi

      local agent_import_path=""
      if agent_import_path="$(extract_option_value --agent-import-path "$@")"; then
        :
      elif [[ "${agent_name}" == "terminus-2" ]]; then
        agent_import_path="libs.terminus_agent.agents.terminus_2.harbor_terminus_2_skills:HarborTerminus2WithSkills"
      fi

      local max_task_attempts
      if max_task_attempts="$(extract_option_value --max-task-attempts "$@")"; then
        :
      else
        max_task_attempts="${SKILLSBENCH_MAX_ATTEMPTS:-1}"
      fi

      local max_parallel_tasks=""
      if max_parallel_tasks="$(extract_option_value --max-parallel-tasks "$@")"; then
        :
      fi

      local agent_kwargs=()
      local ak_values=()
      local agent_kwarg_values=()
      if extract_option_values --ak "$@" >/dev/null; then
        mapfile -d '' -t ak_values < <(extract_option_values --ak "$@")
      fi
      if extract_option_values --agent-kwarg "$@" >/dev/null; then
        mapfile -d '' -t agent_kwarg_values < <(extract_option_values --agent-kwarg "$@")
      fi
      agent_kwargs=("${ak_values[@]}" "${agent_kwarg_values[@]}")

      local early_stop_intra_attempt=0
      if option_supplied --early-stop-intra-attempt "$@"; then
        early_stop_intra_attempt=1
      fi

      local early_stop_strategy=""
      if early_stop_strategy="$(extract_option_value --early-stop-strategy "$@")"; then
        :
      else
        early_stop_strategy="heuristic"
      fi

      local paper_initial_turn_limit=""
      if paper_initial_turn_limit="$(extract_option_value --paper-initial-turn-limit "$@")"; then
        :
      fi

      local paper_extension_turn_limit=""
      if paper_extension_turn_limit="$(extract_option_value --paper-extension-turn-limit "$@")"; then
        :
      fi

      local jobs_root
      if jobs_root="$(extract_option_value --jobs-root "$@")"; then
        :
      else
        jobs_root="$(skillsbench_root)/jobs"
      fi
      if [[ "${jobs_root}" != /* ]]; then
        jobs_root="${REPO_ROOT}/${jobs_root}"
      fi
      mkdir -p "${jobs_root}"

      local job_name=""
      if job_name="$(extract_option_value --job-name "$@")"; then
        :
      fi

      local run_id=""
      if run_id="$(extract_option_value --run-id "$@")"; then
        :
      elif [[ -n "${job_name}" ]]; then
        run_id="${job_name}"
      else
        run_id="$(date +"%Y-%m-%d__%H-%M-%S")"
      fi
      if [[ -z "${job_name}" ]]; then
        job_name="skillsbench-${run_id}"
      fi

      local benchmark_version=""
      if benchmark_version="$(extract_option_value --benchmark-version "$@")"; then
        :
      else
        benchmark_version="skillsbench"
      fi

      local feedback_policy=""
      if feedback_policy="$(extract_option_value --feedback-policy "$@")"; then
        :
      else
        feedback_policy="none"
      fi

      local feedback_format=""
      if feedback_format="$(extract_option_value --feedback-format "$@")"; then
        :
      else
        feedback_format="none"
      fi

      local feedback_strategy=""
      if feedback_strategy="$(extract_option_value --feedback-strategy "$@")"; then
        :
      else
        feedback_strategy="none"
      fi

      local feedback_answer_safety=""
      if feedback_answer_safety="$(extract_option_value --feedback-answer-safety "$@")"; then
        :
      else
        feedback_answer_safety="no-answers"
      fi

      local stop_rule=""
      if stop_rule="$(extract_option_value --stop-rule "$@")"; then
        :
      else
        stop_rule="max-attempts-only"
      fi

      local stop_threshold=""
      if stop_threshold="$(extract_option_value --stop-threshold "$@")"; then
        :
      else
        stop_threshold="0.0"
      fi

      local model_slug
      model_slug="$(printf '%s' "${model_name}" | tr '/.' '--')"
      local output_root="${REPO_ROOT}/${output_dir}"
      mkdir -p "${output_root}"
      local output_json="${output_root}/skillsbench__${model_slug}__${run_id}.json"

      local cmd=(
        -p "${tasks_root}"
        -a "${agent_name}"
        -m "${model_name}"
        --env "${sandbox}"
        -k "${max_task_attempts}"
        --job-name "${job_name}"
        -o "${jobs_root}"
        -y
      )
      if [[ -n "${agent_import_path}" ]]; then
        cmd+=(--agent-import-path "${agent_import_path}")
      fi
      if [[ -n "${max_parallel_tasks}" ]]; then
        cmd+=(-n "${max_parallel_tasks}")
      fi
      if option_supplied --force-build "$@"; then
        cmd+=(--force-build)
      fi
      if option_supplied --no-delete "$@"; then
        cmd+=(--no-delete)
      fi
      local agent_kwarg
      for agent_kwarg in "${agent_kwargs[@]}"; do
        cmd+=(--ak "${agent_kwarg}")
      done
      local task_name
      for task_name in "${task_names[@]}"; do
        cmd+=(-i "${task_name}")
      done

      (
        cd "$(skillsbench_root)"
        if [[ "${early_stop_intra_attempt}" -eq 1 && ${#task_names[@]} -eq 1 ]]; then
          python3 "${REPO_ROOT}/scripts/run_skillsbench_with_early_stop.py" \
            --skillsbench-root "$(skillsbench_root)" \
            --jobs-root "${jobs_root}" \
            --job-name "${job_name}" \
            --task-name "${task_names[0]}" \
            --early-stop-strategy "${early_stop_strategy}" \
            ${paper_initial_turn_limit:+--paper-initial-turn-limit "${paper_initial_turn_limit}"} \
            ${paper_extension_turn_limit:+--paper-extension-turn-limit "${paper_extension_turn_limit}"} \
            -- "${cmd[@]}"
        else
          if [[ "${early_stop_intra_attempt}" -eq 1 ]]; then
            echo "warning: --early-stop-intra-attempt currently supports exactly one SkillsBench task; running without intra-attempt early stop" >&2
          fi
          harbor run "${cmd[@]}"
        fi
      )

      local suite_value
      if [[ ${#task_names[@]} -gt 0 ]]; then
        suite_value="$(IFS=,; printf '%s' "${task_names[*]}")"
      else
        suite_value="$(skillsbench_tasks_prefix "${mode}")"
      fi

      local aggregate_cmd=(
        python3 "${REPO_ROOT}/scripts/aggregate_skillsbench_harbor_results.py"
        --jobs-root "${jobs_root}"
        --job-name "${job_name}"
        --model "${model_name}"
        --agent "${agent_name}"
        --run-id "${run_id}"
        --suite "${suite_value}"
        --max-task-attempts "${max_task_attempts}"
        --benchmark-version "${benchmark_version}"
        --feedback-policy "${feedback_policy}"
        --feedback-format "${feedback_format}"
        --feedback-strategy "${feedback_strategy}"
        --feedback-answer-safety "${feedback_answer_safety}"
        --stop-rule "${stop_rule}"
        --stop-threshold "${stop_threshold}"
        --sandbox "${sandbox}"
        --mode "${mode}"
      )
      if [[ "${early_stop_intra_attempt}" -eq 1 ]]; then
        aggregate_cmd+=(--early-stop-intra-attempt)
      fi
      aggregate_cmd+=(--early-stop-strategy "${early_stop_strategy}")
      aggregate_cmd+=(--output "${output_json}")
      "${aggregate_cmd[@]}"
      ;;
    *)
      echo "Unsupported backend: ${backend}" >&2
      exit 2
      ;;
  esac
}

latest_result_json() {
  local results_dir="$1"
  find "${REPO_ROOT}/${results_dir}" -maxdepth 1 -name '*.json' | sort | tail -n 1
}

result_has_perfect_success() {
  local result_json="$1"
  python3 - "$result_json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

success_rate = float((payload.get("efficiency") or {}).get("success_rate", 0.0) or 0.0)
sys.exit(0 if success_rate >= 1.0 else 1)
PY
}

run_analysis() {
  local results_dir="$1"
  local analysis_dir="$2"
  local label_mode="${3:-policy}"
  (
    cd "${REPO_ROOT}"
    mapfile -t json_files < <(find "${results_dir}" -maxdepth 1 -name '*.json' | sort)
    if [[ ${#json_files[@]} -eq 0 ]]; then
      echo "No result JSON files found in ${results_dir}" >&2
      exit 1
    fi
    python3 scripts/analyze_retries.py "${json_files[@]}" \
      --output-dir "${analysis_dir}" \
      --label-mode "${label_mode}"
  )
}
