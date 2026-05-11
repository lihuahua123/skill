#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from datasets import load_dataset

REPO_ROOT = Path(__file__).resolve().parents[1]
MINISWEAGENT_SRC = REPO_ROOT.parent / "EET" / "mini-swe-agent" / "src"
SKILLSBENCH_ROOT = REPO_ROOT.parent / "skillsbench"
os.environ.setdefault("XDG_CONFIG_HOME", "/tmp/mini_sweagent_config")
sys.path.insert(0, str(MINISWEAGENT_SRC))

from minisweagent.agents.default import DefaultAgent
from minisweagent.agents.experience_retrieval import ExperienceRetrievalAgent
from minisweagent.models import get_model
from minisweagent.models.test_models import DeterministicModel
from minisweagent.run.extra.swebench import get_sb_environment
from minisweagent.run.utils.save import save_traj


def parse_boolish(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run single-attempt SWE-bench evaluation with mini-swe-agent."
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--dataset-path", required=True, type=Path)
    parser.add_argument("--dataset-split", default="test")
    parser.add_argument("--eval-dataset-name", default="")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--swebench-instance-id", default="")
    parser.add_argument("--max-task-attempts", type=int, default=1)
    parser.add_argument("--swebench-agent-backend", choices=("plain-mini", "eet-mini"), default="plain-mini")
    parser.add_argument("--swebench-max-workers", type=int, default=1)
    parser.add_argument("--runner-python", required=True)
    parser.add_argument("--model-class", default="")
    parser.add_argument("--model-output", action="append", default=[])
    parser.add_argument("--feedback-policy", default="error-localized")
    parser.add_argument("--feedback-format", default="full-refresh")
    parser.add_argument("--feedback-answer-safety", default="no-answers")
    parser.add_argument("--stop-rule", default="max-attempts-only")
    parser.add_argument("--stop-threshold", type=float, default=0.0)
    parser.add_argument("--stop-check-early-stop-enabled", default="true")
    parser.add_argument("--stop-check-zero-progress-streak", type=int, default=2)
    parser.add_argument("--stop-check-yes-streak", type=int, default=2)
    parser.add_argument("--skillsbench-skill-guidance", default="false")
    parser.add_argument("--inject-token-efficient-triage-first-prompt", default="false")
    parser.add_argument("--retry-workspace-strategy", choices=("fresh", "preserve"), default="preserve")
    parser.add_argument("--skip-evaluation", action="store_true")
    return parser.parse_args()


def load_instances(dataset_path: Path, split: str) -> list[dict[str, Any]]:
    if dataset_path.suffix == ".parquet":
        dataset = load_dataset("parquet", data_files=str(dataset_path), split="train")
    else:
        dataset = load_dataset(str(dataset_path), split=split)
    return [dict(item) for item in dataset]


def filter_instances(
    instances: list[dict[str, Any]], instance_ids_arg: str
) -> list[dict[str, Any]]:
    if not instance_ids_arg:
        return instances
    wanted = {item.strip() for item in instance_ids_arg.split(",") if item.strip()}
    return [instance for instance in instances if instance["instance_id"] in wanted]


def config_path_for_backend(backend: str) -> Path:
    config_root = MINISWEAGENT_SRC / "minisweagent" / "config" / "extra"
    if backend == "plain-mini":
        return config_root / "swebench.yaml"
    return config_root / "swebench_experience.yaml"


def load_agent_config(backend: str, model_name: str) -> dict[str, Any]:
    config = yaml.safe_load(config_path_for_backend(backend).read_text(encoding="utf-8"))
    config.setdefault("model", {})["model_name"] = model_name
    return config


def inject_agent_section(template: str, heading: str, body: str) -> str:
    section = f"\n\n    ## {heading}\n    {body.replace(chr(10), chr(10) + '    ')}"
    marker = "\n    ## Command Execution Rules"
    if marker in template:
        before, after = template.split(marker, 1)
        return before + section + marker + after
    return template + section


def apply_agent_runtime_settings(
    *,
    config_template: dict[str, Any],
    skill_guidance_enabled: bool,
    stop_check_enabled: bool,
    stop_check_zero_progress_streak: int,
    stop_check_yes_streak: int,
) -> dict[str, Any]:
    config = copy.deepcopy(config_template)
    agent_config = config.setdefault("agent", {})
    agent_config["paper_turn_stopcheck_enabled"] = stop_check_enabled
    agent_config["paper_turn_stopcheck_zero_progress_streak"] = stop_check_zero_progress_streak
    agent_config["paper_turn_stopcheck_yes_streak"] = stop_check_yes_streak
    if skill_guidance_enabled:
        guidance_text = (
            "Use project-specific signals before broad exploration. Prefer targeted grep on identifiers and "
            "error strings from the issue, inspect the most likely implementation files first, and reuse nearby "
            "tests or existing code patterns to constrain the patch."
        )
        agent_config["instance_template"] = inject_agent_section(
            str(agent_config.get("instance_template") or ""),
            "Skill Guidance",
            guidance_text,
        )
    return config


def load_injected_skill_text(skill_name: str) -> str:
    skill_path = SKILLSBENCH_ROOT / "common_skill" / skill_name / "SKILL.md"
    if not skill_path.is_file():
        raise FileNotFoundError(f"Injected skill not found: {skill_path}")
    return skill_path.read_text(encoding="utf-8").strip()


def build_prediction(instance_id: str, model_name: str, patch: str) -> dict[str, Any]:
    return {
        instance_id: {
            "model_name_or_path": model_name,
            "instance_id": instance_id,
            "model_patch": patch,
        }
    }


def _usage_totals_from_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "request_count": 0,
    }
    for message in messages:
        if message.get("role") != "assistant":
            continue
        usage = message.get("usage") or {}
        prompt_tokens = int(usage.get("input", 0) or 0)
        completion_tokens = int(usage.get("output", 0) or 0)
        total_tokens = int(usage.get("totalTokens", 0) or (prompt_tokens + completion_tokens))
        cost_usd = float(((usage.get("cost") or {}).get("total", 0.0)) or 0.0)
        totals["total_prompt_tokens"] += prompt_tokens
        totals["total_completion_tokens"] += completion_tokens
        totals["total_tokens"] += total_tokens
        totals["total_cost_usd"] += cost_usd
        totals["request_count"] += 1
    totals["total_cost_usd"] = round(totals["total_cost_usd"], 6)
    return totals


def _build_usage_per_round(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rounds: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        usage = message.get("usage") or {}
        prompt_tokens = int(usage.get("input", 0) or 0)
        completion_tokens = int(usage.get("output", 0) or 0)
        rounds.append(
            {
                "round": len(rounds) + 1,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": int(usage.get("totalTokens", 0) or (prompt_tokens + completion_tokens)),
                "cost_usd": round(float(((usage.get("cost") or {}).get("total", 0.0)) or 0.0), 6),
            }
        )
    return rounds


def _build_llm_rounds(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rounds: list[dict[str, Any]] = []
    for idx, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        usage = message.get("usage") or {}
        prompt_tokens = int(usage.get("input", 0) or 0)
        completion_tokens = int(usage.get("output", 0) or 0)
        rounds.append(
            {
                "round": len(rounds) + 1,
                "input_messages": copy.deepcopy(messages[:idx]),
                "output_message": copy.deepcopy(message),
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": int(usage.get("totalTokens", 0) or (prompt_tokens + completion_tokens)),
                    "cost_usd": round(float(((usage.get("cost") or {}).get("total", 0.0)) or 0.0), 6),
                },
            }
        )
    return rounds


def _stringify_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _first_round_skill_guidance_metadata(llm_rounds: list[dict[str, Any]]) -> dict[str, Any]:
    if not llm_rounds:
        return {
            "has_first_round": False,
            "prompt_contains_skill_guidance": False,
            "assistant_mentions_skill": False,
        }

    first_round = llm_rounds[0]
    input_messages = list(first_round.get("input_messages") or [])
    output_message = first_round.get("output_message") or {}
    prompt_contains_skill_guidance = any(
        "skill guidance" in _stringify_message_content(message.get("content")).lower()
        for message in input_messages
    )
    assistant_mentions_skill = (
        "skill" in _stringify_message_content(output_message.get("content")).lower()
    )
    return {
        "has_first_round": True,
        "prompt_contains_skill_guidance": prompt_contains_skill_guidance,
        "assistant_mentions_skill": assistant_mentions_skill,
    }


def enforce_skill_guidance_first_round_or_die(
    *,
    llm_rounds: list[dict[str, Any]],
    attempt_number: int,
    skill_guidance_enabled: bool,
) -> dict[str, Any]:
    metadata = _first_round_skill_guidance_metadata(llm_rounds)
    if skill_guidance_enabled and attempt_number == 1 and not metadata["assistant_mentions_skill"]:
        raise RuntimeError("SKILLSBENCH_SKILL_GUIDANCE 为True但是agent没有调用skill")
    return metadata


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def enrich_traj_outputs(
    traj_path: Path,
    attempt_dir: Path,
    *,
    attempt_number: int,
    skill_guidance_enabled: bool,
) -> dict[str, Any]:
    traj_payload = json.loads(traj_path.read_text(encoding="utf-8"))
    messages = list(traj_payload.get("messages") or [])
    usage_totals = _usage_totals_from_messages(messages)
    usage_per_round = _build_usage_per_round(messages)
    llm_rounds = _build_llm_rounds(messages)
    skill_guidance_check = enforce_skill_guidance_first_round_or_die(
        llm_rounds=llm_rounds,
        attempt_number=attempt_number,
        skill_guidance_enabled=skill_guidance_enabled,
    )

    transcript_path = attempt_dir / "transcript.json"
    llm_rounds_path = attempt_dir / "llm_rounds.json"
    _write_json(transcript_path, messages)
    _write_json(llm_rounds_path, llm_rounds)

    traj_payload.update(
        {
            "total_prompt_tokens": usage_totals["total_prompt_tokens"],
            "total_completion_tokens": usage_totals["total_completion_tokens"],
            "total_tokens": usage_totals["total_tokens"],
            "total_cost_usd": usage_totals["total_cost_usd"],
            "request_count": usage_totals["request_count"],
            "usage_per_round": usage_per_round,
            "transcript_path": str(transcript_path),
            "llm_rounds_path": str(llm_rounds_path),
            "skill_guidance_check": skill_guidance_check,
        }
    )
    _write_json(traj_path, traj_payload)

    episode_dirs = sorted(str(path) for path in attempt_dir.glob("episode-*") if path.is_dir())
    extra_trajectories = sorted(
        str(path) for path in attempt_dir.rglob("trajectory.json") if path.resolve() != traj_path.resolve()
    )

    return {
        "transcript_path": str(transcript_path),
        "llm_rounds_path": str(llm_rounds_path),
        "usage": {
            "prompt_tokens": usage_totals["total_prompt_tokens"],
            "completion_tokens": usage_totals["total_completion_tokens"],
            "total_tokens": usage_totals["total_tokens"],
            "cost_usd": usage_totals["total_cost_usd"],
            "request_count": usage_totals["request_count"],
        },
        "usage_per_round": usage_per_round,
        "episode_dirs": episode_dirs,
        "extra_trajectory_files": extra_trajectories,
        "skill_guidance_check": skill_guidance_check,
    }


def _docker_cp_to_env(env: Any, source: Path, destination: str) -> bool:
    container_id = str(getattr(env, "container_id", "") or "").strip()
    docker_executable = str(getattr(getattr(env, "config", None), "executable", "docker") or "docker")
    if not container_id:
        return False
    destination_parent = str(PurePosixPath(destination).parent)
    subprocess.run(
        [docker_executable, "exec", container_id, "mkdir", "-p", destination_parent],
        check=True,
    )
    subprocess.run(
        [docker_executable, "exec", container_id, "rm", "-rf", destination],
        check=True,
    )
    subprocess.run(
        [docker_executable, "cp", str(source), f"{container_id}:{destination}"],
        check=True,
    )
    return True


def _execute_env_command(
    env: Any,
    command: str,
    *,
    cwd: str = "",
    timeout: int | None = None,
    attempts: int = 1,
    retry_delay_seconds: float = 0.5,
) -> dict[str, Any]:
    container_id = str(getattr(env, "container_id", "") or "").strip()
    docker_executable = str(getattr(getattr(env, "config", None), "executable", "docker") or "docker")
    exec_cwd = cwd or str(getattr(getattr(env, "config", None), "cwd", "") or "/")
    if not container_id:
        return env.execute(command, cwd=cwd, timeout=timeout)

    attempt_count = max(int(attempts), 1)
    last_result: dict[str, Any] | None = None
    for attempt_number in range(1, attempt_count + 1):
        cmd = [docker_executable, "exec", "-w", exec_cwd]
        for key in getattr(getattr(env, "config", None), "forward_env", []) or []:
            if (value := os.getenv(key)) is not None:
                cmd.extend(["-e", f"{key}={value}"])
        for key, value in (getattr(getattr(env, "config", None), "env", None) or {}).items():
            cmd.extend(["-e", f"{key}={value}"])
        # Avoid login shell startup files here: some SWE-bench images exit early
        # under `bash -lc`, which breaks retry workspace restoration before the
        # actual restore command even runs.
        cmd.extend([container_id, "bash", "-c", command])
        result = subprocess.run(
            cmd,
            text=True,
            timeout=timeout or getattr(getattr(env, "config", None), "timeout", 30),
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        last_result = {
            "output": result.stdout,
            "returncode": result.returncode,
            "command": shlex.join(cmd),
            "attempt": attempt_number,
        }
        if result.returncode == 0:
            return last_result

        output_text = str(result.stdout or "").strip()
        transient = (
            not output_text
            or "is not running" in output_text
            or "No such container" in output_text
            or "OCI runtime exec failed" in output_text
            or "container" in output_text and "not found" in output_text
        )
        if attempt_number >= attempt_count or not transient:
            return last_result
        time.sleep(retry_delay_seconds * attempt_number)

    return last_result or {"output": "", "returncode": 1}


def _format_command_failure(prefix: str, result: dict[str, Any]) -> str:
    details = [
        prefix,
        f"returncode={int(result.get('returncode', 1) or 1)}",
    ]
    if result.get("attempt"):
        details.append(f"attempt={result.get('attempt')}")
    if result.get("command"):
        details.append(f"exec={result.get('command')}")
    output_text = str(result.get("output") or "").rstrip()
    if output_text:
        details.append(output_text)
    return "\n".join(details)


def _write_file_into_env(env: Any, source: Path, destination: str) -> None:
    if _docker_cp_to_env(env, source, destination):
        return
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    command = (
        "python3 - <<'PY'\n"
        "import base64\n"
        "from pathlib import Path\n"
        f"path = Path({destination!r})\n"
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        f"path.write_bytes(base64.b64decode({encoded!r}))\n"
        "PY"
    )
    result = _execute_env_command(env, command)
    if int(result.get("returncode", 1) or 1) != 0:
        raise RuntimeError(
            _format_command_failure(f"Failed to write file into environment: {destination}", result)
        )


def capture_workspace_snapshot(env: Any, attempt_dir: Path) -> dict[str, str]:
    snapshot_dir = attempt_dir / "workspace_snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    patch_path = snapshot_dir / "workspace.patch"
    untracked_archive_path = snapshot_dir / "untracked.tar.gz"

    diff_result = _execute_env_command(env, "git diff HEAD --binary", cwd="/testbed")
    diff_returncode = int(diff_result.get("returncode", 1) or 1)
    if diff_returncode not in {0, 1}:
        raise RuntimeError(_format_command_failure("Failed to capture workspace patch", diff_result))
    patch_path.write_text(str(diff_result.get("output") or ""), encoding="utf-8")

    untracked_result = _execute_env_command(
        env,
        "python3 - <<'PY'\n"
        "import base64\n"
        "import io\n"
        "import subprocess\n"
        "import sys\n"
        "import tarfile\n"
        "proc = subprocess.run(\n"
        "    ['git', 'ls-files', '--others', '--exclude-standard', '-z'],\n"
        "    stdout=subprocess.PIPE,\n"
        "    stderr=subprocess.PIPE,\n"
        "    check=True,\n"
        ")\n"
        "paths = [item for item in proc.stdout.decode('utf-8', errors='surrogateescape').split('\\0') if item]\n"
        "if not paths:\n"
        "    sys.exit(0)\n"
        "buf = io.BytesIO()\n"
        "with tarfile.open(fileobj=buf, mode='w:gz') as tar:\n"
        "    for rel in paths:\n"
        "        tar.add(rel, arcname=rel)\n"
        "sys.stdout.write(base64.b64encode(buf.getvalue()).decode('ascii'))\n"
        "PY",
        cwd="/testbed",
    )
    if int(untracked_result.get("returncode", 1) or 1) != 0:
        return {
            "patch_path": str(patch_path),
            "untracked_archive_path": "",
            "untracked_capture_error": (
                f"returncode={int(untracked_result.get('returncode', 1) or 1)} "
                f"output={str(untracked_result.get('output') or '').strip()}"
            ),
        }
    encoded_untracked = str(untracked_result.get("output") or "").strip()
    if encoded_untracked:
        untracked_archive_path.write_bytes(base64.b64decode(encoded_untracked))

    return {
        "patch_path": str(patch_path),
        "untracked_archive_path": str(untracked_archive_path) if untracked_archive_path.exists() else "",
        "untracked_capture_error": "",
    }


def restore_workspace_snapshot(env: Any, snapshot: dict[str, str] | None) -> dict[str, Any]:
    if not snapshot:
        return {"restored": False, "restored_from_attempt": None}
    patch_path = Path(snapshot.get("patch_path") or "")
    untracked_archive_path = Path(snapshot.get("untracked_archive_path") or "")
    restore_root = "/tmp/minisweagent_retry_restore"
    reset_restore_root = _execute_env_command(env, f"rm -rf {restore_root} && mkdir -p {restore_root}")
    if int(reset_restore_root.get("returncode", 1) or 1) != 0:
        raise RuntimeError(_format_command_failure("Failed to reset restore workspace", reset_restore_root))

    if patch_path.exists() and patch_path.stat().st_size > 0:
        destination = f"{restore_root}/workspace.patch"
        _write_file_into_env(env, patch_path, destination)
        result = _execute_env_command(env, f"git apply --binary {destination}", cwd="/testbed")
        if int(result.get("returncode", 1) or 1) != 0:
            raise RuntimeError(_format_command_failure("Failed to restore workspace patch", result))

    if untracked_archive_path.exists() and untracked_archive_path.stat().st_size > 0:
        destination = f"{restore_root}/untracked.tar.gz"
        _write_file_into_env(env, untracked_archive_path, destination)
        result = _execute_env_command(
            env,
            "python3 - <<'PY'\n"
            "import tarfile\n"
            f"with tarfile.open({destination!r}, 'r:gz') as tar:\n"
            "    tar.extractall('.')\n"
            "PY",
            cwd="/testbed",
        )
        if int(result.get("returncode", 1) or 1) != 0:
            raise RuntimeError(_format_command_failure("Failed to restore untracked files", result))

    return {
        "restored": True,
        "restored_from_attempt": snapshot.get("attempt_number"),
    }


def _tail_lines(text: str, limit: int = 80) -> str:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(lines[-limit:])


def _strip_pytest_parameterization(test_id: str) -> str:
    if "[" in test_id:
        return test_id.split("[", 1)[0]
    return test_id


def _normalize_failed_test_id(line: str) -> str:
    raw = line.removeprefix("FAILED ").strip()
    if " - " in raw:
        raw = raw.split(" - ", 1)[0].strip()
    return _strip_pytest_parameterization(raw)


def _extract_failed_test_ids(text: str, limit: int = 8) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        candidate = ""
        if stripped.startswith("FAILED "):
            candidate = _normalize_failed_test_id(stripped)
        elif "::" in stripped and (" FAILED" in stripped or " ERROR" in stripped):
            candidate = _strip_pytest_parameterization(stripped.split()[0])
        if candidate and candidate not in seen:
            ids.append(candidate)
            seen.add(candidate)
        if len(ids) >= limit:
            break
    return ids


def _extract_failure_snippets(text: str, max_lines: int = 40) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    failure_lines: list[str] = []
    capture = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("=================================== FAILURES"):
            capture = True
        if capture:
            failure_lines.append(line.rstrip())
        if capture and stripped.startswith("=========================== short test summary info"):
            break
    cleaned = [line for line in failure_lines if line.strip()]
    if not cleaned:
        return ""
    if len(cleaned) > max_lines:
        cleaned = cleaned[:max_lines] + [f"... [{len(cleaned) - max_lines} lines omitted] ..."]
    return "\n".join(cleaned)


def _extract_patch_apply_failure(text: str) -> str:
    match = re.search(
        r">>>>> Patch Apply Failed:\n(?P<body>.*?)(?:\nCheck \(|\Z)",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        return ""
    body = match.group("body").strip()
    if not body:
        return ""
    return "\n".join(line.rstrip() for line in body.splitlines() if line.strip())


def summarize_eval_failure(eval_result: dict[str, Any], answer_safety: str) -> dict[str, Any]:
    del answer_safety
    if eval_result.get("failed_tests") and eval_result.get("notes"):
        return {
            "failed_tests": list(eval_result.get("failed_tests") or []),
            "notes": str(eval_result.get("notes") or ""),
        }
    if eval_result.get("run_instance_log_path"):
        run_instance_log_path = Path(eval_result.get("run_instance_log_path") or "")
        if run_instance_log_path.is_file():
            run_log_text = run_instance_log_path.read_text(encoding="utf-8", errors="replace")
            patch_apply_notes = _extract_patch_apply_failure(run_log_text)
            if patch_apply_notes:
                return {
                    "failed_tests": [],
                    "notes": f"Patch apply failed:\n{patch_apply_notes}",
                }
    test_output_path = Path(eval_result.get("test_output_path") or "")
    test_output = ""
    if test_output_path.is_file():
        test_output = test_output_path.read_text(encoding="utf-8", errors="replace")
    failed_tests = _extract_failed_test_ids(test_output, limit=8)
    snippet = _extract_failure_snippets(test_output, max_lines=40)
    if not snippet:
        snippet = _tail_lines(test_output, limit=40)
    notes = snippet or "Evaluation failed without structured pytest output."
    return {
        "failed_tests": failed_tests,
        "notes": notes,
    }


def build_feedback_prompt(
    *,
    instance: dict[str, Any],
    attempt_number: int,
    eval_result: dict[str, Any],
    summary: dict[str, Any],
    feedback_policy: str,
    feedback_format: str,
) -> dict[str, Any]:
    failed_tests = summary.get("failed_tests") or []
    failed_tests_block = "\n".join(f"- {test_name}" for test_name in failed_tests[:8])
    if not failed_tests_block:
        failed_tests_block = "- No failed test names were extracted."
    notes = summary.get("notes") or "No additional evaluation notes."
    if bool(eval_result.get("stop_check_early_stop")):
        notes = (
            "The previous attempt was early-stopped before evaluation.\n"
            f"{notes}"
        )
    header = (
        f"You are retrying SWE-bench instance `{instance['instance_id']}` after evaluation feedback.\n\n"
        f"Attempt completed: {attempt_number}\n"
        f"Repository: {instance.get('repo', '')}\n"
        f"Base commit: {instance.get('base_commit', '')}\n"
        f"Resolved: {'yes' if bool(eval_result.get('resolved')) else 'no'}\n\n"
    )
    retry_policy = (
        "Fix the specific failing tests first. Avoid unrelated changes.\n"
        "The previous attempt did not fix the target test; compare expected vs actual in the failing assertion, "
        "edit the code path that produces the mismatch, and avoid only changing surface-level error wording.\n"
        "If the same test still fails after your last patch, treat your previous fix direction as incorrect and "
        "choose a different hypothesis instead of refining the same error-message wording.\n"
        "Prioritize the first assertion mismatch over making the message more descriptive."
    )
    if bool(eval_result.get("stop_check_early_stop")):
        retry_policy = (
            "The previous attempt was stopped for low progress. Reassess quickly, inspect the existing edits first, "
            "and choose a more targeted repair path before broad exploration."
        )
    if feedback_policy == "vague":
        body = (
            "The previous attempt did not resolve the instance.\n\n"
            "Retry policy:\n"
            f"{retry_policy}"
        )
    else:
        body = (
            "Failed tests:\n"
            f"{failed_tests_block}\n\n"
            "Evaluation notes:\n"
            f"{notes}\n\n"
            "Retry policy:\n"
            f"{retry_policy}"
        )
    if feedback_format == "stable-prefix":
        stable_prefix = (
            f"You are working on SWE-bench instance `{instance['instance_id']}`.\n\n"
            "Use the latest evaluation failure symptoms to repair the patch.\n"
            "Avoid unrelated changes and do not assume hidden reference answers."
        )
        dynamic_suffix = f"\n\nLatest evaluation result:\n{body}"
        text = stable_prefix + dynamic_suffix
        return {
            "text": text,
            "text_length_chars": len(text),
            "stable_prefix_length_chars": len(stable_prefix),
            "dynamic_suffix_length_chars": len(dynamic_suffix),
            "unresolved_criteria_count": 0 if bool(eval_result.get("resolved")) else 1,
            "feedback_format": feedback_format,
        }
    text = header + body
    return {
        "text": text,
        "text_length_chars": len(text),
        "stable_prefix_length_chars": 0,
        "dynamic_suffix_length_chars": len(text),
        "unresolved_criteria_count": 0 if bool(eval_result.get("resolved")) else 1,
        "feedback_format": feedback_format,
    }


def compose_attempt_instruction(
    original_problem_statement: str,
    feedback_prompt: str | None,
    retry_workspace_strategy: str,
) -> str:
    preserve_note = ""
    if retry_workspace_strategy == "preserve":
        preserve_note = (
            "Retry workspace note:\n"
            "- You are continuing from the previous attempt's modified workspace.\n"
            "- Inspect existing source edits before creating new ones.\n"
            "- Reuse and repair in-place unless the earlier direction is clearly wrong.\n\n"
        )
    if not feedback_prompt:
        return f"{preserve_note}{original_problem_statement}" if preserve_note else original_problem_statement
    return (
        f"{preserve_note}{feedback_prompt}\n\n"
        "Original problem statement:\n"
        f"{original_problem_statement}"
    )


def compose_initial_instruction_with_injected_skill(
    *,
    original_problem_statement: str,
    injected_skill_text: str,
    injected_skill_name: str,
) -> str:
    return (
        "Startup skill to follow before broad exploration:\n"
        f"[Injected skill: {injected_skill_name}]\n"
        f"{injected_skill_text}\n\n"
        "Original task instruction:\n"
        f"{original_problem_statement}"
    )


def should_stop_retry(
    *,
    stop_rule: str,
    stop_threshold: float,
    current_score: float,
    previous_score: float | None,
    token_delta: float,
) -> str | None:
    if stop_rule == "max-attempts-only":
        return None
    if previous_score is None:
        return None
    score_delta = round(float(current_score) - float(previous_score), 6)
    if stop_rule in {"no-improvement", "score-stall"} and score_delta <= stop_threshold:
        return "score-stall"
    if stop_rule == "token-stall" and score_delta <= 0 and token_delta > 0:
        return "token-stall"
    return None


def wait_for_env_cleanup(env: Any, timeout_seconds: float = 10.0) -> None:
    cleanup = getattr(env, "cleanup", None)
    if not callable(cleanup):
        return
    container_id = str(getattr(env, "container_id", "") or "").strip()
    docker_executable = str(getattr(getattr(env, "config", None), "executable", "docker") or "docker")
    cleanup()
    if not container_id:
        return
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = subprocess.run(
            [docker_executable, "inspect", container_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            return
        time.sleep(0.2)


def build_task_attempt_summary(
    *,
    attempt_number: int,
    traj_path: Path,
    prediction_path: Path,
    eval_result_path: Path,
    feedback_path: Path | None,
    feedback_prompt: str | None,
    feedback_stats: dict[str, Any] | None,
    feedback_policy: str,
    feedback_format: str,
    agent_time_seconds: float,
    evaluation_time_seconds: float,
    resolved: bool,
    stop_rule: str,
    stop_threshold: float,
    stop_rule_trigger_reason: str | None,
    transcript_path: Path | None,
    llm_rounds_path: Path | None,
    usage: dict[str, Any] | None,
    usage_per_round: list[dict[str, Any]] | None,
    episode_dirs: list[str] | None,
    extra_trajectory_files: list[str] | None,
    retry_workspace_strategy: str,
    workspace_snapshot: dict[str, str] | None,
    workspace_restore: dict[str, Any] | None,
    stop_check: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "attempt": attempt_number,
        "traj_json": str(traj_path),
        "prediction_json": str(prediction_path),
        "eval_json": str(eval_result_path),
        "transcript_json": str(transcript_path) if transcript_path else "",
        "llm_rounds_json": str(llm_rounds_path) if llm_rounds_path else "",
        "feedback_path": str(feedback_path) if feedback_path else "",
        "feedback_prompt": feedback_prompt,
        "feedback_prompt_stats": feedback_stats,
        "feedback_policy": feedback_policy,
        "feedback_format": feedback_format,
        "agent_time_seconds": agent_time_seconds,
        "evaluation_time_seconds": evaluation_time_seconds,
        "resolved": resolved,
        "stop_rule": stop_rule,
        "stop_threshold": stop_threshold,
        "stop_rule_trigger_reason": stop_rule_trigger_reason,
        "usage": usage or {},
        "usage_per_round": usage_per_round or [],
        "episode_dirs": episode_dirs or [],
        "extra_trajectory_files": extra_trajectory_files or [],
        "retry_workspace_strategy": retry_workspace_strategy,
        "workspace_snapshot": workspace_snapshot or {},
        "workspace_restore": workspace_restore or {},
        "stop_check": stop_check or {},
    }


def run_single_attempt(
    *,
    instance: dict[str, Any],
    model_name: str,
    backend: str,
    config_template: dict[str, Any],
    attempt_dir: Path,
    env: Any,
    attempt_number: int,
    skill_guidance_enabled: bool,
) -> tuple[Path, Path, float, dict[str, Any], str, str, dict[str, str] | None, dict[str, Any]]:
    instance_id = instance["instance_id"]
    config = copy.deepcopy(config_template)
    workspace_snapshot = None
    workspace_restore = {
        "restored": False,
        "restored_from_attempt": None,
        "reused_container": True,
    }
    if config["model"].get("model_class") == "deterministic":
        deterministic_model_config = dict(config["model"])
        deterministic_model_config.pop("model_class", None)
        model = DeterministicModel(**deterministic_model_config)
    else:
        model = get_model(config=config["model"])
    try:
        agent_config = config.get("agent", {})
        task = instance["problem_statement"]

        started_at = time.time()
        if backend == "plain-mini":
            agent = DefaultAgent(model, env, **agent_config)
            exit_status, result = agent.run(task)
        else:
            agent = ExperienceRetrievalAgent(model, env, **agent_config)
            exit_status, result = agent.run(task, issue_id=instance_id)
        finished_at = time.time()

        traj_path = attempt_dir / "traj.json"
        save_traj(
            agent,
            traj_path,
            exit_status=exit_status,
            result=result,
            extra_info={
                "stop_check": {
                    "enabled": bool(getattr(agent, "_paper_turn_stopcheck_enabled", False)),
                    "history": list(getattr(agent, "stop_check_history", [])),
                    "stop_triggered": bool(getattr(agent, "stop_check_stop_triggered", False)),
                    "stop_reason": getattr(agent, "stop_check_stop_reason", None),
                },
                "workspace_restore": workspace_restore,
            },
            instance_id=instance_id,
            print_path=False,
        )
        traj_metadata = enrich_traj_outputs(
            traj_path,
            attempt_dir,
            attempt_number=attempt_number,
            skill_guidance_enabled=skill_guidance_enabled,
        )
        traj_metadata["workspace_snapshot"] = workspace_snapshot
        traj_metadata["workspace_restore"] = workspace_restore
        traj_metadata["stop_check"] = {
            "enabled": bool(getattr(agent, "_paper_turn_stopcheck_enabled", False)),
            "history": list(getattr(agent, "stop_check_history", [])),
            "stop_triggered": bool(getattr(agent, "stop_check_stop_triggered", False)),
            "stop_reason": getattr(agent, "stop_check_stop_reason", None),
        }

        prediction_path = attempt_dir / "prediction.json"
        prediction_path.write_text(
            json.dumps(build_prediction(instance_id, model_name, result), indent=2),
            encoding="utf-8",
        )
        return (
            traj_path,
            prediction_path,
            finished_at - started_at,
            traj_metadata,
            exit_status,
            result,
            workspace_snapshot,
            workspace_restore,
        )
    finally:
        pass


def run_evaluation(
    *,
    runner_python: str,
    eval_dataset_name: str,
    prediction_path: Path,
    model_name: str,
    run_id: str,
    split: str,
    instance_id: str,
    max_workers: int,
    output_root: Path,
    attempt_dir: Path,
    answer_safety: str,
) -> tuple[Path, float]:
    runner_python = str(Path(runner_python).absolute())
    eval_started_at = time.time()
    subprocess.run(
        [
            runner_python,
            "-m",
            "swebench.harness.run_evaluation",
            "--dataset_name",
            eval_dataset_name,
            "--predictions_path",
            str(prediction_path),
            "--max_workers",
            str(max_workers),
            "--run_id",
            run_id,
        ],
        check=True,
        cwd=str(output_root),
    )
    eval_finished_at = time.time()

    model_log_name = model_name.replace("/", "__")
    report_path = (
        output_root / "logs" / "run_evaluation" / run_id / model_log_name / instance_id / "report.json"
    )
    run_instance_log_path = (
        output_root / "logs" / "run_evaluation" / run_id / model_log_name / instance_id / "run_instance.log"
    )
    test_output_path = (
        output_root / "logs" / "run_evaluation" / run_id / model_log_name / instance_id / "test_output.txt"
    )
    report: dict[str, Any] = {}
    resolved = False
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        resolved = bool(report[instance_id]["resolved"])
    failure_summary = summarize_eval_failure(
        {
            "test_output_path": str(test_output_path),
            "run_instance_log_path": str(run_instance_log_path),
        },
        answer_safety,
    )

    eval_result_path = attempt_dir / "eval_result.json"
    eval_result_path.write_text(
        json.dumps(
            {
                "instance_id": instance_id,
                "run_id": run_id,
                "split": split,
                "resolved": resolved,
                "report_path": str(report_path) if report_path.exists() else "",
                "test_output_path": str(test_output_path),
                "run_instance_log_path": str(run_instance_log_path) if run_instance_log_path.exists() else "",
                "evaluation_time_seconds": eval_finished_at - eval_started_at,
                "report": report,
                "notes": failure_summary["notes"],
                "failed_tests": failure_summary["failed_tests"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return eval_result_path, eval_finished_at - eval_started_at


def main() -> None:
    args = parse_args()

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(output_root / ".hf_cache"))

    instances = filter_instances(load_instances(args.dataset_path.resolve(), args.dataset_split), args.swebench_instance_id)
    config_template = apply_agent_runtime_settings(
        config_template=load_agent_config(args.swebench_agent_backend, args.model),
        skill_guidance_enabled=parse_boolish(args.skillsbench_skill_guidance),
        stop_check_enabled=parse_boolish(args.stop_check_early_stop_enabled),
        stop_check_zero_progress_streak=args.stop_check_zero_progress_streak,
        stop_check_yes_streak=args.stop_check_yes_streak,
    )
    inject_token_efficient_triage_first_prompt = parse_boolish(args.inject_token_efficient_triage_first_prompt)
    injected_skill_name = "swebench-token-efficient-repair"
    injected_skill_text = (
        load_injected_skill_text(injected_skill_name)
        if inject_token_efficient_triage_first_prompt
        else None
    )
    if args.model_class:
        config_template.setdefault("model", {})["model_class"] = args.model_class
    if args.model_output:
        config_template.setdefault("model", {})["outputs"] = args.model_output
    if args.model_class == "deterministic":
        config_template["model"].pop("model_kwargs", None)
        config_template["model"].pop("set_cache_control", None)

    for instance in instances:
        instance_id = instance["instance_id"]
        instance_root = output_root / instance_id
        instance_root.mkdir(parents=True, exist_ok=True)
        original_problem_statement = str(instance["problem_statement"])
        previous_score: float | None = None
        stop_reason = "max-attempts-reached"
        first_success_attempt: int | None = None
        attempt_summaries: list[dict[str, Any]] = []
        shared_env = None
        try:
            if args.retry_workspace_strategy == "preserve":
                shared_env = get_sb_environment(config_template, instance)

            for attempt_number in range(1, max(1, args.max_task_attempts) + 1):
                attempt_dir = instance_root / f"attempt_{attempt_number}"
                attempt_dir.mkdir(parents=True, exist_ok=True)
                feedback_prompt = None
                feedback_stats = None
                feedback_path: Path | None = None
                attempt_instance = dict(instance)
                if attempt_number == 1 and injected_skill_text:
                    attempt_instance["problem_statement"] = compose_initial_instruction_with_injected_skill(
                        original_problem_statement=original_problem_statement,
                        injected_skill_text=injected_skill_text,
                        injected_skill_name=injected_skill_name,
                    )
                elif attempt_summaries:
                    previous_eval_result = json.loads(
                        Path(attempt_summaries[-1]["eval_json"]).read_text(encoding="utf-8")
                    )
                    previous_feedback_summary = summarize_eval_failure(
                        previous_eval_result,
                        args.feedback_answer_safety,
                    )
                    feedback_stats = build_feedback_prompt(
                        instance=instance,
                        attempt_number=attempt_number - 1,
                        eval_result=previous_eval_result,
                        summary=previous_feedback_summary,
                        feedback_policy=args.feedback_policy,
                        feedback_format=args.feedback_format,
                    )
                    feedback_prompt = feedback_stats["text"]
                    feedback_path = attempt_dir / "feedback.txt"
                    feedback_path.write_text(feedback_prompt, encoding="utf-8")
                    attempt_instance["problem_statement"] = compose_attempt_instruction(
                        original_problem_statement,
                        feedback_prompt,
                        args.retry_workspace_strategy,
                    )
                elif args.retry_workspace_strategy == "preserve":
                    attempt_instance["problem_statement"] = compose_attempt_instruction(
                        original_problem_statement,
                        None,
                        args.retry_workspace_strategy,
                    )

                attempt_env = shared_env
                if attempt_env is None:
                    attempt_env = get_sb_environment(config_template, instance)

                try:
                    (
                        traj_path,
                        prediction_path,
                        agent_time,
                        traj_metadata,
                        exit_status,
                        exit_message,
                        workspace_snapshot,
                        workspace_restore,
                    ) = run_single_attempt(
                        instance=attempt_instance,
                        model_name=args.model,
                        backend=args.swebench_agent_backend,
                        config_template=config_template,
                        attempt_dir=attempt_dir,
                        env=attempt_env,
                        attempt_number=attempt_number,
                        skill_guidance_enabled=parse_boolish(args.skillsbench_skill_guidance),
                    )
                finally:
                    if shared_env is None:
                        wait_for_env_cleanup(attempt_env)

                if exit_status == "StopCheckTerminated":
                    eval_result_path = attempt_dir / "eval_result.json"
                    eval_result = {
                        "instance_id": instance_id,
                        "run_id": "",
                        "split": args.dataset_split,
                        "resolved": False,
                        "report_path": "",
                        "test_output_path": "",
                        "run_instance_log_path": "",
                        "evaluation_time_seconds": 0.0,
                        "report": {},
                        "notes": exit_message,
                        "failed_tests": [],
                        "skipped": True,
                        "stop_check_early_stop": True,
                    }
                    eval_result_path.write_text(json.dumps(eval_result, indent=2), encoding="utf-8")
                    attempt_summaries.append(
                        build_task_attempt_summary(
                            attempt_number=attempt_number,
                            traj_path=traj_path,
                            prediction_path=prediction_path,
                            eval_result_path=eval_result_path,
                            feedback_path=feedback_path,
                            feedback_prompt=feedback_prompt,
                            feedback_stats=feedback_stats,
                            feedback_policy=args.feedback_policy,
                            feedback_format=args.feedback_format,
                            agent_time_seconds=agent_time,
                            evaluation_time_seconds=0.0,
                            resolved=False,
                            stop_rule=args.stop_rule,
                            stop_threshold=args.stop_threshold,
                            stop_rule_trigger_reason="intra-attempt-early-stop",
                            transcript_path=Path(traj_metadata["transcript_path"]),
                            llm_rounds_path=Path(traj_metadata["llm_rounds_path"]),
                            usage=traj_metadata["usage"],
                            usage_per_round=traj_metadata["usage_per_round"],
                            episode_dirs=traj_metadata["episode_dirs"],
                            extra_trajectory_files=traj_metadata["extra_trajectory_files"],
                            retry_workspace_strategy=args.retry_workspace_strategy,
                            workspace_snapshot=workspace_snapshot,
                            workspace_restore=workspace_restore,
                            stop_check=traj_metadata["stop_check"],
                        )
                    )
                    previous_score = 0.0
                    if attempt_number >= max(1, args.max_task_attempts):
                        stop_reason = "intra-attempt-early-stop"
                        break
                    continue

                if args.skip_evaluation:
                    eval_result_path = attempt_dir / "eval_result.json"
                    eval_result = {
                        "instance_id": instance_id,
                        "run_id": "",
                        "split": args.dataset_split,
                        "resolved": False,
                        "report_path": "",
                        "test_output_path": "",
                        "evaluation_time_seconds": 0.0,
                        "report": {},
                        "skipped": True,
                    }
                    eval_result_path.write_text(
                        json.dumps(eval_result, indent=2),
                        encoding="utf-8",
                    )
                    evaluation_time = 0.0
                    stop_reason = "evaluation-skipped"
                    attempt_summaries.append(
                        build_task_attempt_summary(
                            attempt_number=attempt_number,
                            traj_path=traj_path,
                            prediction_path=prediction_path,
                            eval_result_path=eval_result_path,
                            feedback_path=feedback_path,
                            feedback_prompt=feedback_prompt,
                            feedback_stats=feedback_stats,
                            feedback_policy=args.feedback_policy,
                            feedback_format=args.feedback_format,
                            agent_time_seconds=agent_time,
                            evaluation_time_seconds=evaluation_time,
                            resolved=False,
                            stop_rule=args.stop_rule,
                            stop_threshold=args.stop_threshold,
                            stop_rule_trigger_reason="evaluation-skipped",
                            transcript_path=Path(traj_metadata["transcript_path"]),
                            llm_rounds_path=Path(traj_metadata["llm_rounds_path"]),
                            usage=traj_metadata["usage"],
                            usage_per_round=traj_metadata["usage_per_round"],
                            episode_dirs=traj_metadata["episode_dirs"],
                            extra_trajectory_files=traj_metadata["extra_trajectory_files"],
                            retry_workspace_strategy=args.retry_workspace_strategy,
                            workspace_snapshot=workspace_snapshot,
                            workspace_restore=workspace_restore,
                            stop_check=traj_metadata["stop_check"],
                        )
                    )
                    break
                if not args.eval_dataset_name:
                    raise ValueError("--eval-dataset-name is required unless --skip-evaluation is set")
                eval_run_id = f"{args.run_id}__{instance_id}__attempt_{attempt_number}"
                eval_result_path, evaluation_time = run_evaluation(
                    runner_python=args.runner_python,
                    eval_dataset_name=args.eval_dataset_name,
                    prediction_path=prediction_path,
                    model_name=args.model,
                    run_id=eval_run_id,
                    split=args.dataset_split,
                    instance_id=instance_id,
                    max_workers=args.swebench_max_workers,
                    output_root=output_root,
                    attempt_dir=attempt_dir,
                    answer_safety=args.feedback_answer_safety,
                )
                eval_result = json.loads(eval_result_path.read_text(encoding="utf-8"))
                current_score = 1.0 if bool(eval_result["resolved"]) else 0.0
                token_delta = float((traj_metadata.get("usage") or {}).get("total_tokens", 0) or 0.0)
                stop_trigger = should_stop_retry(
                    stop_rule=args.stop_rule,
                    stop_threshold=args.stop_threshold,
                    current_score=current_score,
                    previous_score=previous_score,
                    token_delta=token_delta,
                )

                attempt_summaries.append(
                    build_task_attempt_summary(
                        attempt_number=attempt_number,
                        traj_path=traj_path,
                        prediction_path=prediction_path,
                        eval_result_path=eval_result_path,
                        feedback_path=feedback_path,
                        feedback_prompt=feedback_prompt,
                        feedback_stats=feedback_stats,
                        feedback_policy=args.feedback_policy,
                        feedback_format=args.feedback_format,
                        agent_time_seconds=agent_time,
                        evaluation_time_seconds=evaluation_time,
                        resolved=bool(eval_result["resolved"]),
                        stop_rule=args.stop_rule,
                        stop_threshold=args.stop_threshold,
                        stop_rule_trigger_reason=stop_trigger,
                        transcript_path=Path(traj_metadata["transcript_path"]),
                        llm_rounds_path=Path(traj_metadata["llm_rounds_path"]),
                        usage=traj_metadata["usage"],
                        usage_per_round=traj_metadata["usage_per_round"],
                        episode_dirs=traj_metadata["episode_dirs"],
                        extra_trajectory_files=traj_metadata["extra_trajectory_files"],
                        retry_workspace_strategy=args.retry_workspace_strategy,
                        workspace_snapshot=workspace_snapshot,
                        workspace_restore=workspace_restore,
                        stop_check=traj_metadata["stop_check"],
                    )
                )

                if current_score >= 1.0:
                    first_success_attempt = attempt_number
                    stop_reason = "passed"
                    break
                if stop_trigger is not None:
                    stop_reason = stop_trigger
                    break
                previous_score = current_score
        finally:
            if shared_env is not None:
                wait_for_env_cleanup(shared_env)

        task_summary = {
            "task_id": instance_id,
            "attempt_count": len(attempt_summaries),
            "first_success_attempt": first_success_attempt,
            "success_within_budget": first_success_attempt is not None,
            "stop_reason": stop_reason,
            "swebench_agent_backend": args.swebench_agent_backend,
            "model": args.model,
            "skillsbench_skill_guidance": parse_boolish(args.skillsbench_skill_guidance),
            "inject_token_efficient_triage_first_prompt": inject_token_efficient_triage_first_prompt,
            "retry_workspace_strategy": args.retry_workspace_strategy,
            "stop_check": {
                "enabled": parse_boolish(args.stop_check_early_stop_enabled),
                "zero_progress_streak": args.stop_check_zero_progress_streak,
                "yes_streak": args.stop_check_yes_streak,
                "triggered_attempts": [
                    attempt["attempt"]
                    for attempt in attempt_summaries
                    if bool((attempt.get("stop_check") or {}).get("stop_triggered"))
                ],
            },
            "retry_policies": {
                "feedback_policy": args.feedback_policy,
                "feedback_format": args.feedback_format,
                "feedback_strategy": "swebench-safe",
                "feedback_answer_safety": args.feedback_answer_safety,
                "stop_rule": args.stop_rule,
                "stop_threshold": args.stop_threshold,
                "max_task_attempts": max(1, args.max_task_attempts),
                "stop_check_early_stop_enabled": parse_boolish(args.stop_check_early_stop_enabled),
                "stop_check_zero_progress_streak": args.stop_check_zero_progress_streak,
                "stop_check_yes_streak": args.stop_check_yes_streak,
                "skillsbench_skill_guidance": parse_boolish(args.skillsbench_skill_guidance),
                "inject_token_efficient_triage_first_prompt": inject_token_efficient_triage_first_prompt,
                "retry_workspace_strategy": args.retry_workspace_strategy,
            },
            "usage": {
                "prompt_tokens": sum(int((attempt.get("usage") or {}).get("prompt_tokens", 0) or 0) for attempt in attempt_summaries),
                "completion_tokens": sum(
                    int((attempt.get("usage") or {}).get("completion_tokens", 0) or 0) for attempt in attempt_summaries
                ),
                "total_tokens": sum(int((attempt.get("usage") or {}).get("total_tokens", 0) or 0) for attempt in attempt_summaries),
                "cost_usd": round(
                    sum(float((attempt.get("usage") or {}).get("cost_usd", 0.0) or 0.0) for attempt in attempt_summaries),
                    6,
                ),
                "request_count": sum(int((attempt.get("usage") or {}).get("request_count", 0) or 0) for attempt in attempt_summaries),
            },
            "total_prompt_tokens": sum(
                int((attempt.get("usage") or {}).get("prompt_tokens", 0) or 0) for attempt in attempt_summaries
            ),
            "total_completion_tokens": sum(
                int((attempt.get("usage") or {}).get("completion_tokens", 0) or 0) for attempt in attempt_summaries
            ),
            "total_tokens": sum(int((attempt.get("usage") or {}).get("total_tokens", 0) or 0) for attempt in attempt_summaries),
            "usage_per_round": [
                {
                    **round_item,
                    "attempt": attempt_summary["attempt"],
                }
                for attempt_summary in attempt_summaries
                for round_item in (attempt_summary.get("usage_per_round") or [])
            ],
            "attempts": attempt_summaries,
        }
        (instance_root / "task_summary.json").write_text(
            json.dumps(task_summary, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
