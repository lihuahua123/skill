from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .types import ExecutionAnalysis, EvolutionSuggestion, EvolutionType, SkillLineageRecord, SkillOrigin


DEFAULT_PARENT_SKILL_ID = "pinchbench-retry-core"


def evolve_analyses(
    analyses: Iterable[ExecutionAnalysis],
    *,
    generated_skills_dir: Path,
    backup_dir: Path,
    skill_usage_index: Optional[Dict[str, Dict[str, str]]] = None,
    apply_fixes: bool = False,
) -> List[SkillLineageRecord]:
    records: List[SkillLineageRecord] = []
    generated_skills_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    usage_index = skill_usage_index or {}

    for analysis in analyses:
        for suggestion in analysis.evolution_suggestions:
            record = _materialize_suggestion(
                analysis,
                suggestion,
                generated_skills_dir,
                backup_dir,
                usage_index,
                apply_fixes,
            )
            records.append(record)
    return records


def _materialize_suggestion(
    analysis: ExecutionAnalysis,
    suggestion: EvolutionSuggestion,
    generated_skills_dir: Path,
    backup_dir: Path,
    skill_usage_index: Dict[str, Dict[str, str]],
    apply_fixes: bool,
) -> SkillLineageRecord:
    skill_name = _skill_name_for_suggestion(analysis, suggestion)
    skill_id = f"{skill_name}__{_short_hash(analysis.analysis_id + suggestion.direction)}"
    content = _render_skill_content(skill_name, analysis, suggestion, skill_id)
    materialization = _resolve_materialization_target(
        analysis,
        suggestion,
        generated_skills_dir,
        backup_dir,
        skill_usage_index,
        skill_name,
        apply_fixes,
    )
    skill_dir = materialization["skill_dir"]
    skill_path = materialization["skill_path"]
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(content, encoding="utf-8")

    lineage_path = materialization["lineage_path"]
    lineage = SkillLineageRecord(
        skill_id=skill_id,
        skill_name=skill_name,
        origin=_to_origin(suggestion.evolution_type),
        parent_skill_ids=suggestion.target_skill_ids or (
            [DEFAULT_PARENT_SKILL_ID] if suggestion.evolution_type != EvolutionType.CAPTURED else []
        ),
        source_task_id=analysis.task_id,
        source_analysis_id=analysis.analysis_id,
        change_summary=materialization["change_summary"],
        generated_path=str(skill_path),
        content_snapshot={"SKILL.md": content},
    )
    lineage_path.write_text(json.dumps(lineage.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return lineage


def _render_skill_content(
    skill_name: str,
    analysis: ExecutionAnalysis,
    suggestion: EvolutionSuggestion,
    skill_id: str,
) -> str:
    title = skill_name.replace("-", " ")
    parent_skills = ", ".join(suggestion.target_skill_ids) if suggestion.target_skill_ids else "(none)"
    return f"""---
name: {skill_name}
description: Offline-evolved skill generated from historical benchmark data.
category: {suggestion.category}
skill_id: {skill_id}
origin: {_to_origin(suggestion.evolution_type).value}
parent_skill_ids:
{_yaml_list(suggestion.target_skill_ids)}
source_task_id: {analysis.task_id}
source_analysis_id: {analysis.analysis_id}
---

# {title}

## Why this exists

This skill was generated using an OpenSpace-style evolution flow:

1. historical execution records were analyzed
2. an evolution suggestion was created
3. the suggestion was materialized as a versioned skill

## Evolution Type

`{suggestion.evolution_type.value}`

## Parent Skills

{parent_skills}

## Direction

{suggestion.direction}

## Rationale

{suggestion.rationale}

## Source Evidence

- benchmark: `{analysis.benchmark}`
- task: `{analysis.task_id}`
- note: `{analysis.execution_note}`

## Workflow

1. Read the verifier-visible failure before changing strategy.
2. Check output-contract and artifact existence before broad rewrites.
3. Preserve successful intermediate artifacts and only patch the narrow mismatch.
4. Stop repeated retries when the failure class is unchanged.
5. Escalate to a new task-family-specific method when the loop is not converging.

## Task-Family Guidance

- If the task touches structured artifacts such as PDFs, XLSX, or generated reports, validate the artifact first.
- If the task is planning-heavy or search-heavy, avoid repeating the same long-horizon strategy after two similar failures.
- If the verifier identifies one narrow mismatch, patch that mismatch instead of restarting the whole task.
"""


def _skill_name_for_suggestion(analysis: ExecutionAnalysis, suggestion: EvolutionSuggestion) -> str:
    if suggestion.evolution_type == EvolutionType.CAPTURED:
        return _slugify(f"{analysis.benchmark}-{analysis.task_id}-captured")
    if suggestion.evolution_type == EvolutionType.FIX:
        return _slugify(f"{analysis.benchmark}-retry-core-fixed")
    return _slugify(f"{analysis.benchmark}-{analysis.task_id}-derived")


def build_skill_usage_index(task_skill_usage: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    index: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for item in task_skill_usage.get("tasks", []):
        benchmark = str(item.get("benchmark", ""))
        task_id = str(item.get("task_id", ""))
        if not benchmark or not task_id:
            continue
        key = f"{benchmark}:{task_id}"
        mapping: Dict[str, Dict[str, Any]] = {}
        for skill in item.get("skills", []):
            name = _slugify(str(skill.get("skill_name", "")))
            path = str(skill.get("skill_dir", ""))
            if name and path and name not in mapping:
                mapping[name] = {
                    "path": path,
                    "evidence_types": list(skill.get("evidence_types", [])),
                }
        index[key] = mapping
    return index


def _resolve_materialization_target(
    analysis: ExecutionAnalysis,
    suggestion: EvolutionSuggestion,
    generated_skills_dir: Path,
    backup_dir: Path,
    skill_usage_index: Dict[str, Dict[str, Dict[str, Any]]],
    skill_name: str,
    apply_fixes: bool,
) -> Dict[str, Any]:
    if suggestion.evolution_type != EvolutionType.FIX or not apply_fixes:
        skill_dir = generated_skills_dir / skill_name
        return {
            "skill_dir": skill_dir,
            "skill_path": skill_dir / "SKILL.md",
            "lineage_path": skill_dir / "lineage.json",
            "change_summary": (
                suggestion.direction
                if suggestion.evolution_type != EvolutionType.FIX or apply_fixes
                else suggestion.direction + " Emitted as a fix candidate; in-place replacement disabled."
            ),
        }

    usage_key = f"{analysis.benchmark}:{analysis.task_id}"
    path_map = skill_usage_index.get(usage_key, {})
    target_dir: Optional[Path] = None
    target_skill_id = ""
    for candidate in suggestion.target_skill_ids:
        candidate_info = path_map.get(candidate)
        if not candidate_info:
            continue
        candidate_dir = str(candidate_info.get("path", ""))
        evidence_types = set(candidate_info.get("evidence_types", []))
        if (
            analysis.benchmark != "skillsbench"
            or not candidate_dir.startswith("/root/.claude/skills/")
            or not {"skill_loaded", "skill_script_invoked"} & evidence_types
        ):
            continue
        if candidate_dir:
            target_dir = Path(candidate_dir)
            target_skill_id = candidate
            break
    if target_dir is None:
        skill_dir = generated_skills_dir / skill_name
        return {
            "skill_dir": skill_dir,
            "skill_path": skill_dir / "SKILL.md",
            "lineage_path": skill_dir / "lineage.json",
            "change_summary": suggestion.direction,
        }
    if not target_dir.exists():
        skill_dir = generated_skills_dir / skill_name
        return {
            "skill_dir": skill_dir,
            "skill_path": skill_dir / "SKILL.md",
            "lineage_path": skill_dir / "lineage.json",
            "change_summary": (
                f"{suggestion.direction} Intended parent {target_skill_id or target_dir.name} "
                "was not present on disk, so the fix was emitted as a generated fallback."
            ),
        }

    backup_target = backup_dir / (
        f"{target_dir.name}__{_short_hash(str(target_dir))}__"
        f"{_short_hash(analysis.analysis_id + suggestion.direction)}"
    )
    if backup_target.exists():
        shutil.rmtree(backup_target)
    shutil.copytree(target_dir, backup_target)
    return {
        "skill_dir": target_dir,
        "skill_path": target_dir / "SKILL.md",
        "lineage_path": target_dir / "evo_lineage.json",
        "change_summary": (
            f"{suggestion.direction} Replaced original skill in place; "
            f"backup stored at {backup_target} for parent {target_skill_id or target_dir.name}."
        ),
    }


def _to_origin(evolution_type: EvolutionType) -> SkillOrigin:
    if evolution_type == EvolutionType.FIX:
        return SkillOrigin.FIXED
    if evolution_type == EvolutionType.DERIVED:
        return SkillOrigin.DERIVED
    return SkillOrigin.CAPTURED


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "evolved-skill"


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]


def _yaml_list(values: List[str]) -> str:
    if not values:
        return "  []"
    return "\n".join(f"  - {value}" for value in values)
