from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

SKILL_PATH_PATTERNS = (
    re.compile(r"(/root/\.openclaw/skills/[^/\s\"']+(?:/[^\s\"']+)*)"),
    re.compile(r"(/root/skillsbench/tasks/[^/\s\"']+/environment/skills/[^/\s\"']+(?:/[^\s\"']+)*)"),
    re.compile(r"(/root/\.codex/skills/[^/\s\"']+(?:/[^\s\"']+)*)"),
    re.compile(r"(/root/\.agents/skills/[^/\s\"']+(?:/[^\s\"']+)*)"),
    re.compile(r"(/root/skillsbench/\.claude/skills/[^/\s\"']+(?:/[^\s\"']+)*)"),
)


def extract_skill_usage_from_results(results_dir: Path) -> Dict[str, Any]:
    task_map: Dict[str, Dict[str, Any]] = {}
    for path in sorted(results_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for result in _normalize_payload(payload):
            benchmark = _infer_benchmark(path.name, result)
            for task in result.get("tasks", []):
                task_id = str(task.get("task_id", "unknown-task"))
                key = f"{benchmark}:{task_id}"
                entry = task_map.setdefault(
                    key,
                    {
                        "benchmark": benchmark,
                        "task_id": task_id,
                        "source_files": set(),
                        "skill_dirs": defaultdict(lambda: _empty_skill_record()),
                    },
                )
                entry["source_files"].add(str(path))
                for attempt in task.get("attempts", []):
                    transcript = attempt.get("execution", {}).get("transcript")
                    for skill_path, evidence in _extract_skill_paths(transcript):
                        skill_dir, rel_path = _normalize_skill_path(skill_path)
                        record = entry["skill_dirs"][skill_dir]
                        record["files"].add(rel_path)
                        record["raw_paths"].add(skill_path)
                        record["evidence_types"].add(evidence)
                for skill_dir, rel_path, evidence in _extract_external_skill_usage(task):
                    record = entry["skill_dirs"][skill_dir]
                    record["files"].add(rel_path)
                    record["raw_paths"].add(str(Path(skill_dir) / rel_path) if rel_path else skill_dir)
                    record["evidence_types"].add(evidence)
    return _finalize(task_map)


def _normalize_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("series"), list):
        return [item for item in payload["series"] if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _infer_benchmark(filename: str, result: Dict[str, Any]) -> str:
    benchmark = result.get("benchmark")
    if benchmark:
        return str(benchmark)
    if "skillsbench" in filename:
        return "skillsbench"
    return "pinchbench"


def _extract_skill_paths(transcript: Any) -> Iterable[Tuple[str, str]]:
    seen: set[Tuple[str, str]] = set()
    for text, evidence in _iter_strings(transcript):
        for pattern in SKILL_PATH_PATTERNS:
            for match in pattern.findall(text):
                normalized = match.rstrip(".,:;)")
                key = (normalized, evidence)
                if key not in seen:
                    seen.add(key)
                    yield key


def _extract_external_skill_usage(task: Dict[str, Any]) -> Iterable[Tuple[str, str, str]]:
    source_job = task.get("source_job")
    source_trial = task.get("source_trial")
    if not source_job or not source_trial:
        return []
    trial_dir = Path("/root/skillsbench/jobs") / str(source_job) / str(source_trial)
    if not trial_dir.exists():
        return []
    return list(_extract_from_trial_dir(trial_dir))


def _extract_from_trial_dir(trial_dir: Path) -> Iterable[Tuple[str, str, str]]:
    available_locations: Dict[str, str] = {}
    loaded_skill_locations: List[str] = []
    for trajectory_path in sorted(trial_dir.glob("agent/attempt-*/trajectory.json")):
        try:
            entries = json.loads(trajectory_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            prompt = entry.get("prompt")
            if isinstance(prompt, str):
                for name, location in _extract_available_skills(prompt).items():
                    available_locations[name] = location
                for name in _extract_loaded_skill_names(prompt):
                    location = available_locations.get(name)
                    if not location:
                        continue
                    loaded_skill_locations.append(location)
                    yield location, "SKILL.md", "skill_loaded"
            response = entry.get("response")
            for skill_path, evidence in _extract_skill_paths(response):
                skill_dir, rel_path = _normalize_skill_path(skill_path)
                yield skill_dir, rel_path, evidence
    for attempt_dir in sorted(trial_dir.glob("agent/attempt-*")):
        yield from _extract_from_attempt_dir(attempt_dir, available_locations, loaded_skill_locations)


def _extract_from_attempt_dir(
    attempt_dir: Path,
    available_locations: Dict[str, str],
    loaded_skill_locations: List[str],
) -> Iterable[Tuple[str, str, str]]:
    for path in sorted(attempt_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in {"trajectory.json"}:
            continue
        if path.suffix.lower() not in {".txt", ".json", ".md"}:
            continue
        text = _read_text(path)
        if text is None:
            continue
        for name, location in _extract_available_skills(text).items():
            available_locations[name] = location
        for name in _extract_loaded_skill_names(text):
            location = available_locations.get(name)
            if location:
                loaded_skill_locations.append(location)
                yield location, "SKILL.md", "skill_loaded"
        for skill_path, evidence in _extract_skill_paths(text):
            skill_dir, rel_path = _normalize_skill_path(skill_path)
            yield skill_dir, rel_path, evidence
        for relative_file in _extract_skill_local_file_mentions(text):
            guessed = _guess_loaded_skill_for_file(relative_file, loaded_skill_locations)
            if guessed:
                skill_dir, rel_path = guessed
                yield skill_dir, rel_path, "skill_auxiliary_file_used"


def _extract_available_skills(prompt: str) -> Dict[str, str]:
    marker = "available_skills:"
    if marker not in prompt:
        return {}
    tail = prompt.split(marker, 1)[1]
    start = tail.find("[")
    end = tail.find("]\nLOADED SKILLS:")
    if start == -1 or end == -1:
        return {}
    raw = tail[start : end + 1]
    try:
        skills = json.loads(raw)
    except Exception:
        return {}
    mapping: Dict[str, str] = {}
    for item in skills:
        if isinstance(item, dict) and item.get("name") and item.get("location"):
            mapping[str(item["name"])] = str(item["location"])
    return mapping


def _extract_loaded_skill_names(prompt: str) -> List[str]:
    names: List[str] = []
    for line in prompt.splitlines():
        if line.startswith("Loaded skill: "):
            names.append(line.split("Loaded skill: ", 1)[1].strip())
    return names


def _extract_skill_local_file_mentions(text: str) -> List[str]:
    matches = re.findall(r"\['LICENSE\.txt', 'SKILL\.md', [^\]]+\]", text)
    if matches:
        # Common pattern from prompt.txt after loading a skill; prefer canonical sidecars.
        files = re.findall(r"'([^']+)'", matches[0])
        return [item for item in files if item not in {"LICENSE.txt", "SKILL.md"}]
    files = re.findall(r"\b(?:reference\.md|forms\.md|README\.md|scripts/[A-Za-z0-9._/\-]+)\b", text)
    return files


def _guess_loaded_skill_for_file(
    relative_file: str,
    loaded_skill_locations: List[str],
) -> Tuple[str, str] | None:
    if not loaded_skill_locations:
        return None
    last_location = loaded_skill_locations[-1]
    return last_location, relative_file


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None
    except Exception:
        return None


def _iter_strings(value: Any, *, parent_key: str = "") -> Iterable[Tuple[str, str]]:
    if isinstance(value, str):
        evidence = _evidence_type(parent_key, value)
        yield value, evidence
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_strings(item, parent_key=parent_key)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_strings(item, parent_key=str(key))


def _evidence_type(parent_key: str, value: str) -> str:
    lowered = value.lower()
    key = parent_key.lower()
    if "skill.md" in lowered:
        return "skill_definition_read"
    if key == "command" or "/scripts/" in lowered:
        return "skill_script_invoked"
    if key == "path":
        return "skill_file_opened"
    return "skill_reference"


def _normalize_skill_path(path_str: str) -> Tuple[str, str]:
    path = Path(path_str)
    parts = path.parts
    if "/environment/skills/" in path_str:
        idx = parts.index("skills")
        skill_dir = str(Path(*parts[: idx + 2]))
        rel_path = str(Path(*parts[idx + 2 :])) if len(parts) > idx + 2 else "SKILL.md"
        return skill_dir, rel_path
    if "/skills/" in path_str:
        idx = parts.index("skills")
        skill_dir = str(Path(*parts[: idx + 2]))
        rel_path = str(Path(*parts[idx + 2 :])) if len(parts) > idx + 2 else "SKILL.md"
        return skill_dir, rel_path
    return path_str, path.name


def _empty_skill_record() -> Dict[str, Any]:
    return {
        "files": set(),
        "raw_paths": set(),
        "evidence_types": set(),
    }


def _finalize(task_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    tasks: List[Dict[str, Any]] = []
    for key in sorted(task_map):
        entry = task_map[key]
        skills: List[Dict[str, Any]] = []
        for skill_dir, record in sorted(entry["skill_dirs"].items()):
            skills.append(
                {
                    "skill_dir": skill_dir,
                    "skill_name": Path(skill_dir).name,
                    "files": sorted(record["files"]),
                    "raw_paths": sorted(record["raw_paths"]),
                    "evidence_types": sorted(record["evidence_types"]),
                }
            )
        tasks.append(
            {
                "benchmark": entry["benchmark"],
                "task_id": entry["task_id"],
                "source_files": sorted(entry["source_files"]),
                "skills": skills,
            }
        )
    return {"tasks": tasks}
