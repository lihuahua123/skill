#!/usr/bin/env python3
"""Rule-based direct reuse program for task_21_openclaw_comprehension."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pdfplumber


def extract_pdf_text(pdf_path: Path) -> str:
    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return "\n\n".join(pages)


def require_match(pattern: str, text: str, label: str, flags: int = re.IGNORECASE) -> re.Match[str]:
    match = re.search(pattern, text, flags)
    if not match:
        raise ValueError(f"Could not extract {label} from PDF text.")
    return match


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract task 21 answers without an LLM.")
    parser.add_argument("--pdf", required=True, help="Path to openclaw_report.pdf")
    parser.add_argument("--output", required=True, help="Path to answer.txt")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    output_path = Path(args.output)
    text = extract_pdf_text(pdf_path)

    total_skills = require_match(r"public registry had\s+([\d,]+)\s+community-built skills", text, "total skills").group(1)
    filtered_skills = require_match(r"includes\s+([\d,]+)\s+after excluding suspected spam", text, "filtered skills").group(1)
    top_category = require_match(
        r"AI\s*&\s*LLM\w*(?:\s+meta-tools)?\s*[\(:]\s*(\d+)\)?",
        text,
        "top category count",
    )
    second_category = require_match(
        r"Search\s*&\s*Research\s*[\(:]\s*(\d+)\)?",
        text,
        "second category count",
    )
    skill_filename = require_match(r"\b(SKILL\.md)\b", text, "skill filename").group(1)
    api_type = require_match(r"exposing a\s+(typed WebSocket API)", text, "API type").group(1)
    collected_date = require_match(r"as of\s+(February\s+7,\s+2026)", text, "collection date").group(1)

    proposed_tasks = [
        "Secure skill installation and safe configuration",
        "Browser automation with",
        "Multi-channel routing and session isolation",
        "Scheduled daily briefing with data fusion + memory write-back",
        "PR review and repair loop with CI feedback",
        "Prompt-injection and tool-blast-radius containment",
    ]
    proposed_count = sum(1 for title in proposed_tasks if title.lower() in text.lower())
    if proposed_count != 6:
        raise ValueError(f"Expected 6 proposed tasks, found {proposed_count}.")

    answers = [
        total_skills.replace(",", ""),
        filtered_skills.replace(",", ""),
        f"AI & LLMs: {top_category.group(1)}",
        f"Search & Research: {second_category.group(1)}",
        skill_filename,
        api_type,
        collected_date,
        str(proposed_count),
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(answers) + "\n")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
