from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, List

from .analyzer import analyze_results, load_result_records, load_task_skill_usage
from .evolver import build_skill_usage_index, evolve_analyses
from .skill_usage import extract_skill_usage_from_results
from .types import ExecutionAnalysis, SkillLineageRecord


ROOT = Path(__file__).resolve().parent
DEFAULT_RESULTS_DIR = ROOT.parent / "results" / "rq1"
DEFAULT_STORE_DIR = ROOT / "store"
DEFAULT_ANALYSIS_FILE = DEFAULT_STORE_DIR / "execution_analyses.jsonl"
DEFAULT_LINEAGE_FILE = DEFAULT_STORE_DIR / "skill_lineage.jsonl"
DEFAULT_GENERATED_SKILLS_DIR = ROOT / "generated_skills"
DEFAULT_SKILL_USAGE_FILE = DEFAULT_STORE_DIR / "task_skill_usage.json"
DEFAULT_BACKUP_DIR = ROOT / "original_skills_backup"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline OpenSpace-style skill evolution")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze historical benchmark results")
    analyze.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    analyze.add_argument("--analysis-file", default=str(DEFAULT_ANALYSIS_FILE))
    analyze.add_argument("--skill-usage-file", default=str(DEFAULT_SKILL_USAGE_FILE))
    analyze.add_argument("--benchmark-filter", choices=("pinchbench", "skillsbench"))

    evolve = subparsers.add_parser("evolve", help="Generate skill drafts from stored analyses")
    evolve.add_argument("--analysis-file", default=str(DEFAULT_ANALYSIS_FILE))
    evolve.add_argument("--lineage-file", default=str(DEFAULT_LINEAGE_FILE))
    evolve.add_argument("--generated-skills-dir", default=str(DEFAULT_GENERATED_SKILLS_DIR))
    evolve.add_argument("--skill-usage-file", default=str(DEFAULT_SKILL_USAGE_FILE))
    evolve.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    evolve.add_argument("--apply-fixes", action="store_true")

    run = subparsers.add_parser("run", help="Analyze and evolve in one step")
    run.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    run.add_argument("--analysis-file", default=str(DEFAULT_ANALYSIS_FILE))
    run.add_argument("--lineage-file", default=str(DEFAULT_LINEAGE_FILE))
    run.add_argument("--generated-skills-dir", default=str(DEFAULT_GENERATED_SKILLS_DIR))
    run.add_argument("--skill-usage-file", default=str(DEFAULT_SKILL_USAGE_FILE))
    run.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    run.add_argument("--benchmark-filter", choices=("pinchbench", "skillsbench"))
    run.add_argument("--apply-fixes", action="store_true")

    usage = subparsers.add_parser("skill-usage", help="Extract per-task actual skill usage from results")
    usage.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    usage.add_argument("--output-json", default=str(DEFAULT_STORE_DIR / "task_skill_usage.json"))

    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "analyze":
        analyses = run_analysis(
            Path(args.results_dir),
            Path(args.skill_usage_file),
            benchmark_filter=args.benchmark_filter,
        )
        write_jsonl(Path(args.analysis_file), (item.to_dict() for item in analyses))
        print(f"wrote {len(analyses)} analyses to {args.analysis_file}")
        return

    if args.command == "evolve":
        analyses = load_analyses(Path(args.analysis_file))
        lineages = run_evolution(
            analyses,
            Path(args.generated_skills_dir),
            Path(args.backup_dir),
            Path(args.skill_usage_file),
            apply_fixes=args.apply_fixes,
        )
        write_jsonl(Path(args.lineage_file), (item.to_dict() for item in lineages))
        print(f"wrote {len(lineages)} lineage records to {args.lineage_file}")
        return

    if args.command == "skill-usage":
        data = extract_skill_usage_from_results(Path(args.results_dir))
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {len(data['tasks'])} task skill-usage records to {output_path}")
        return

    analyses = run_analysis(
        Path(args.results_dir),
        Path(args.skill_usage_file),
        benchmark_filter=args.benchmark_filter,
    )
    write_jsonl(Path(args.analysis_file), (item.to_dict() for item in analyses))
    lineages = run_evolution(
        analyses,
        Path(args.generated_skills_dir),
        Path(args.backup_dir),
        Path(args.skill_usage_file),
        apply_fixes=args.apply_fixes,
    )
    write_jsonl(Path(args.lineage_file), (item.to_dict() for item in lineages))
    print(
        f"wrote {len(analyses)} analyses to {args.analysis_file} and "
        f"{len(lineages)} lineage records to {args.lineage_file}"
    )


def run_analysis(
    results_dir: Path,
    skill_usage_file: Path | None = None,
    *,
    benchmark_filter: str | None = None,
) -> List[ExecutionAnalysis]:
    records = load_result_records(results_dir)
    usage = load_task_skill_usage(skill_usage_file) if skill_usage_file else {}
    return analyze_results(records, task_skill_usage=usage, benchmark_filter=benchmark_filter)


def run_evolution(
    analyses: Iterable[ExecutionAnalysis],
    generated_skills_dir: Path,
    backup_dir: Path,
    skill_usage_file: Path | None = None,
    *,
    apply_fixes: bool = False,
) -> List[SkillLineageRecord]:
    usage_payload = (
        json.loads(skill_usage_file.read_text(encoding="utf-8"))
        if skill_usage_file and skill_usage_file.exists()
        else {"tasks": []}
    )
    usage_index = build_skill_usage_index(usage_payload)
    return evolve_analyses(
        analyses,
        generated_skills_dir=generated_skills_dir,
        backup_dir=backup_dir,
        skill_usage_index=usage_index,
        apply_fixes=apply_fixes,
    )


def load_analyses(path: Path) -> List[ExecutionAnalysis]:
    analyses: List[ExecutionAnalysis] = []
    if not path.exists():
        return analyses
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            analyses.append(
                ExecutionAnalysis(
                    analysis_id=raw["analysis_id"],
                    benchmark=raw["benchmark"],
                    source_file=raw["source_file"],
                    task_id=raw["task_id"],
                    task_completed=raw["task_completed"],
                    execution_note=raw["execution_note"],
                    metrics=raw.get("metrics", {}),
                    evolution_suggestions=[
                        _raw_suggestion_to_obj(item) for item in raw.get("evolution_suggestions", [])
                    ],
                    created_at=raw.get("created_at", ""),
                )
            )
    return analyses


def _raw_suggestion_to_obj(raw: dict):
    from .types import EvolutionSuggestion, EvolutionType

    return EvolutionSuggestion(
        evolution_type=EvolutionType(raw["evolution_type"]),
        target_skill_ids=list(raw.get("target_skill_ids", [])),
        category=raw.get("category", "workflow"),
        direction=raw.get("direction", ""),
        rationale=raw.get("rationale", ""),
    )


def write_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")


if __name__ == "__main__":
    main()
