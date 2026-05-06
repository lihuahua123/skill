#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PREFERRED_SKILL_PATH_SUFFIXES = (
    "/.claude/skills",
    "/.codex/skills",
    "/.opencode/skill",
    "/.agents/skills",
    "/.goose/skills",
    "/.factory/skills",
    "/.gemini/skills",
    "/.github/skills",
    "/.cursor/skills",
    "/skills",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ensure docker-backed SkillsBench tasks expose environment.skills_dir in task.toml."
    )
    parser.add_argument("--skillsbench-root", required=True, type=Path)
    parser.add_argument(
        "--task-name",
        action="append",
        dest="task_names",
        default=[],
        help="Task name relative to <skillsbench-root>/tasks/",
    )
    parser.add_argument(
        "--task-path",
        action="append",
        dest="task_paths",
        default=[],
        help="Explicit task directory path.",
    )
    return parser.parse_args()


def _normalize_container_path(path: str) -> str:
    normalized = path.strip().rstrip("/")
    return normalized or path.strip()


def _extract_skills_copy_destinations(dockerfile_text: str) -> list[str]:
    destinations: list[str] = []
    for raw_line in dockerfile_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.upper().startswith("COPY "):
            continue
        match = re.match(r"^COPY\s+(.+?)\s+(\S+)\s*$", line, re.IGNORECASE)
        if not match:
            continue
        source, destination = match.groups()
        source = source.strip()
        if source not in {"skills", "skills/"}:
            continue
        destinations.append(_normalize_container_path(destination))
    return destinations


def detect_container_skills_dir(task_dir: Path) -> str | None:
    dockerfile = task_dir / "environment" / "Dockerfile"
    if not dockerfile.exists():
        return None

    dockerfile_text = dockerfile.read_text(encoding="utf-8")
    destinations = _extract_skills_copy_destinations(dockerfile_text)
    if not destinations:
        return None

    for suffix in PREFERRED_SKILL_PATH_SUFFIXES:
        for destination in destinations:
            if destination.endswith(suffix):
                return destination

    return destinations[0]


def _replace_or_insert_environment_skills_dir(task_toml_text: str, skills_dir: str) -> str:
    env_match = re.search(r"(?ms)^\[environment\]\n(?P<body>.*?)(?=^\[|\Z)", task_toml_text)
    if env_match is None:
        return task_toml_text

    body = env_match.group("body")
    updated_line = f'skills_dir = "{skills_dir}"'
    if re.search(r"(?m)^skills_dir\s*=.*$", body):
        new_body = re.sub(r"(?m)^skills_dir\s*=.*$", updated_line, body)
    else:
        suffix = "" if not body or body.endswith("\n") else "\n"
        new_body = f"{body}{suffix}{updated_line}\n"

    start, end = env_match.span("body")
    return task_toml_text[:start] + new_body + task_toml_text[end:]


def ensure_task_skills_dir(task_dir: Path) -> bool:
    skills_root = task_dir / "environment" / "skills"
    if not skills_root.is_dir():
        return False

    task_toml = task_dir / "task.toml"
    if not task_toml.exists():
        return False

    skills_dir = detect_container_skills_dir(task_dir)
    if not skills_dir:
        return False

    original = task_toml.read_text(encoding="utf-8")
    updated = _replace_or_insert_environment_skills_dir(original, skills_dir)
    if updated == original:
        return False

    task_toml.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    args = parse_args()

    task_dirs: list[Path] = []
    task_dirs.extend(args.skillsbench_root / "tasks" / name for name in args.task_names)
    task_dirs.extend(Path(path) for path in args.task_paths)

    changed: list[str] = []
    for task_dir in task_dirs:
        if ensure_task_skills_dir(task_dir):
            changed.append(str(task_dir))

    if changed:
        for task_dir in changed:
            print(f"[skills-dir] updated {task_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
