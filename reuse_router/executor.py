#!/usr/bin/env python3
"""Execute a compiled reuse program directly without calling an LLM."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any


ROOT = Path(__file__).resolve().parent


@dataclass
class StepResult:
    step: int
    action: str
    status: str
    details: dict[str, Any]


def render_value(value: Any, slots: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return Template(value).safe_substitute(slots)
    if isinstance(value, list):
        return [render_value(item, slots) for item in value]
    if isinstance(value, dict):
        return {key: render_value(item, slots) for key, item in value.items()}
    return value


def action_mkdir(params: dict[str, Any]) -> dict[str, Any]:
    path = Path(params["path"])
    path.mkdir(parents=params.get("parents", True), exist_ok=params.get("exist_ok", True))
    return {"path": str(path)}


def action_write_text(params: dict[str, Any]) -> dict[str, Any]:
    path = Path(params["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    content = params["content"]
    path.write_text(content)
    return {"path": str(path), "bytes": len(content.encode())}


def action_append_text(params: dict[str, Any]) -> dict[str, Any]:
    path = Path(params["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    content = params["content"]
    with path.open("a") as handle:
        handle.write(content)
    return {"path": str(path), "bytes_appended": len(content.encode())}


def action_copy_file(params: dict[str, Any]) -> dict[str, Any]:
    src = Path(params["src"])
    dst = Path(params["dst"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {"src": str(src), "dst": str(dst)}


def action_replace_text(params: dict[str, Any]) -> dict[str, Any]:
    path = Path(params["path"])
    old = params["old"]
    new = params["new"]
    count = int(params.get("count", -1))
    content = path.read_text()
    updated = content.replace(old, new, count)
    path.write_text(updated)
    return {"path": str(path), "replaced": old, "replacement": new}


def action_regex_replace(params: dict[str, Any]) -> dict[str, Any]:
    path = Path(params["path"])
    pattern = params["pattern"]
    replacement = params["replacement"]
    count = int(params.get("count", 0))
    content = path.read_text()
    updated, replacements = re.subn(pattern, replacement, content, count=count)
    path.write_text(updated)
    return {"path": str(path), "pattern": pattern, "replacement_count": replacements}


def action_assert_exists(params: dict[str, Any]) -> dict[str, Any]:
    path = Path(params["path"])
    if not path.exists():
        raise FileNotFoundError(f"Expected path does not exist: {path}")
    return {"path": str(path)}


def action_assert_contains(params: dict[str, Any]) -> dict[str, Any]:
    path = Path(params["path"])
    needle = params["needle"]
    content = path.read_text()
    if needle not in content:
        raise ValueError(f"Expected `{needle}` in {path}")
    return {"path": str(path), "needle": needle}


def action_run_command(params: dict[str, Any]) -> dict[str, Any]:
    cmd = params["cmd"]
    cwd = params.get("cwd")
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        shell=False,
        check=True,
        text=True,
        capture_output=True,
    )
    return {
        "cmd": cmd,
        "cwd": cwd,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returncode": completed.returncode,
    }


ACTIONS = {
    "mkdir": action_mkdir,
    "write_text": action_write_text,
    "append_text": action_append_text,
    "copy_file": action_copy_file,
    "replace_text": action_replace_text,
    "regex_replace": action_regex_replace,
    "assert_exists": action_assert_exists,
    "assert_contains": action_assert_contains,
    "run_command": action_run_command,
}


def execute_program(program: dict[str, Any]) -> dict[str, Any]:
    slots = program.get("slots", {})
    compiled_steps = program.get("compiled_steps", [])
    results: list[StepResult] = []

    for index, raw_step in enumerate(compiled_steps, start=1):
        action = raw_step["action"]
        if action not in ACTIONS:
            raise ValueError(f"Unsupported action: {action}")
        params = render_value(raw_step.get("params", {}), slots)
        details = ACTIONS[action](params)
        results.append(
            StepResult(
                step=index,
                action=action,
                status="ok",
                details=details,
            )
        )

    return {
        "program_id": program.get("program_id"),
        "mode": program.get("mode", "template_reuse"),
        "status": "completed",
        "step_results": [
            {
                "step": result.step,
                "action": result.action,
                "status": result.status,
                "details": result.details,
            }
            for result in results
        ],
    }


def load_program(args: argparse.Namespace) -> dict[str, Any]:
    if args.program_json:
        program = json.loads(args.program_json)
    elif args.program_file:
        program = json.loads(Path(args.program_file).read_text())
    else:
        raise SystemExit("Provide either --program-json or --program-file.")
    if args.slots_json:
        slots_override = json.loads(args.slots_json)
        program.setdefault("slots", {}).update(slots_override)
    return program


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute a compiled reuse program without an LLM.")
    parser.add_argument("--program-json", default=None, help="Inline JSON object for the compiled reuse program.")
    parser.add_argument("--program-file", default=None, help="Path to a compiled reuse program JSON file.")
    parser.add_argument("--slots-json", default=None, help="Inline JSON object merged into program slots before execution.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print execution output.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    program = load_program(args)
    result = execute_program(program)
    if args.pretty:
        print(json.dumps(result, indent=2, ensure_ascii=True))
    else:
        print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
