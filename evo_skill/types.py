from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvolutionType(str, Enum):
    FIX = "fix"
    DERIVED = "derived"
    CAPTURED = "captured"


class SkillOrigin(str, Enum):
    IMPORTED = "imported"
    FIXED = "fixed"
    DERIVED = "derived"
    CAPTURED = "captured"


@dataclass
class SkillJudgment:
    skill_id: str
    skill_applied: bool = False
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvolutionSuggestion:
    evolution_type: EvolutionType
    target_skill_ids: List[str] = field(default_factory=list)
    category: str = "workflow"
    direction: str = ""
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["evolution_type"] = self.evolution_type.value
        return data


@dataclass
class ExecutionAnalysis:
    analysis_id: str
    benchmark: str
    source_file: str
    task_id: str
    task_completed: bool
    execution_note: str
    skill_judgments: List[SkillJudgment] = field(default_factory=list)
    evolution_suggestions: List[EvolutionSuggestion] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "benchmark": self.benchmark,
            "source_file": self.source_file,
            "task_id": self.task_id,
            "task_completed": self.task_completed,
            "execution_note": self.execution_note,
            "skill_judgments": [item.to_dict() for item in self.skill_judgments],
            "evolution_suggestions": [item.to_dict() for item in self.evolution_suggestions],
            "metrics": self.metrics,
            "created_at": self.created_at,
        }


@dataclass
class SkillLineageRecord:
    skill_id: str
    skill_name: str
    origin: SkillOrigin
    parent_skill_ids: List[str] = field(default_factory=list)
    source_task_id: Optional[str] = None
    source_analysis_id: Optional[str] = None
    change_summary: str = ""
    generated_path: str = ""
    content_snapshot: Dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["origin"] = self.origin.value
        return data
