from __future__ import annotations

import argparse
import json
from pathlib import Path

from .skill_usage import extract_skill_usage_from_results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract per-task skill usage from historical results")
    parser.add_argument("--results-dir", default="/root/skill/results/rq1")
    parser.add_argument("--output-json", default="/root/skill/evo_skill/store/task_skill_usage.json")
    parser.add_argument("--output-md", default="/root/skill/evo_skill/store/task_skill_usage.md")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    data = extract_skill_usage_from_results(Path(args.results_dir))
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.output_md).write_text(_render_markdown(data), encoding="utf-8")
    print(f"wrote {len(data['tasks'])} task records to {output_json}")


def _render_markdown(data: dict) -> str:
    lines = ["# Task Skill Usage", ""]
    for task in data.get("tasks", []):
        lines.append(f"## {task['benchmark']} / {task['task_id']}")
        if not task.get("skills"):
            lines.append("")
            lines.append("- no skill evidence found")
            lines.append("")
            continue
        lines.append("")
        for skill in task["skills"]:
            ev = ", ".join(skill["evidence_types"])
            files = ", ".join(skill["files"][:6]) if skill["files"] else "(root only)"
            lines.append(f"- `{skill['skill_name']}`")
            lines.append(f"  dir: `{skill['skill_dir']}`")
            lines.append(f"  evidence: {ev}")
            lines.append(f"  files: {files}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
