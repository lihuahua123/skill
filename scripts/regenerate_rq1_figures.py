#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib as mpl


ROOT = Path("/root")
PINCHBENCH_MINIMAX = ROOT / "skill/results/rq1/pinchbench_minimax-cn-MiniMax-M2-5__merged.json"
PINCHBENCH_GPT = ROOT / "skill/results/rq1/pinchbench_autodl-gpt-5-3-codex.json"
SKILLSBENCH_MINIMAX = ROOT / "skill/results/rq1/skillsbench__minimax-cn-MiniMax-M2-5__merged_with_token_patch.json"
SKILLSBENCH_GPT = ROOT / "skill/results/rq1/skillsbench__openai-gpt-5-3-codex__2026-03-28__19-58-04.json"
FIGURES_DIR = ROOT / "neurips_2026_template/figures"

SHARED_SKILLSBENCH_TASKS = [
    "threejs-structure-parser",
    "python-scala-translation",
    "fix-build-google-auto",
    "fix-build-agentops",
    "court-form-filling",
    "dialogue-parser",
    "powerlifting-coef-calc",
    "earthquake-phase-association",
    "dapt-intrusion-detection",
    "setup-fuzzing-py",
    "software-dependency-audit",
    "suricata-custom-exfil",
    "r2r-mpc-control",
    "energy-market-pricing",
    "financial-modeling-qa",
    "find-topk-similiar-chemicals",
    "react-performance-debugging",
    "glm-lake-mendota",
    "lake-warming-attribution",
    "latex-formula-extraction",
    "lean4-proof",
    "manufacturing-equipment-maintenance",
    "manufacturing-codebook-normalization",
    "mars-clouds-clustering",
    "offer-letter-generator",
    "parallel-tfidf-search",
    "pedestrian-traffic-counting",
    "quantum-numerical-simulation",
    "shock-analysis-demand",
    "reserves-at-risk-calc",
    "sec-financial-report",
    "spring-boot-jakarta-migration",
]

mpl.rcParams.update(
    {
        "font.size": 14,
        "axes.titlesize": 18,
        "axes.labelsize": 16,
        "xtick.labelsize": 13,
        "ytick.labelsize": 13,
        "legend.fontsize": 14,
        "axes.linewidth": 1.2,
    }
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def success_curve(tasks: list[dict], max_attempts: int = 6) -> list[float]:
    total = len(tasks)
    values = []
    for k in range(1, max_attempts + 1):
        successes = 0
        for task in tasks:
            first_success_attempt = task.get("first_success_attempt")
            if first_success_attempt is not None and int(first_success_attempt) <= k:
                successes += 1
        values.append(successes / total if total else 0.0)
    return values


def marginal_gain(curve: list[float]) -> list[float]:
    prev = 0.0
    out = []
    for value in curve:
        out.append(value - prev)
        prev = value
    return out


def pick_tasks(payload: dict, allowed_task_ids: list[str] | None = None) -> list[dict]:
    tasks = payload.get("tasks", []) or []
    if allowed_task_ids is None:
        return tasks
    allowed = set(allowed_task_ids)
    picked = [task for task in tasks if task.get("task_id") in allowed]
    missing = sorted(allowed - {task.get("task_id") for task in picked})
    if missing:
        raise ValueError(f"Missing tasks: {missing}")
    return picked


def plot_success_at_k(pinch_gpt: list[float], pinch_minimax: list[float], skills_gpt: list[float], skills_minimax: list[float]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 4.6), sharey=True)
    xs = list(range(1, 7))

    panels = [
        ("PinchBench-23", pinch_gpt, pinch_minimax),
        ("SkillsBench-32", skills_gpt, skills_minimax),
    ]
    for ax, (title, gpt, minimax) in zip(axes, panels):
        ax.plot(xs, gpt, marker="o", linewidth=2.9, markersize=9, color="#c73b2a", label="GPT-5.3-Codex")
        ax.plot(xs, minimax, marker="o", linewidth=2.9, markersize=9, color="#2c7fb8", label="MiniMax-M2.5")
        ax.set_title(title)
        ax.set_xlabel("Attempt")
        ax.set_ylabel("Cumulative success rate")
        ax.set_xticks(xs)
        ax.set_ylim(0, 1)
        ax.grid(alpha=0.25, linewidth=1.0)
        ax.tick_params(length=4, width=1.1)
        ax.legend(frameon=False, loc="upper right", handlelength=2.2)

    fig.subplots_adjust(left=0.07, right=0.995, top=0.90, bottom=0.16, wspace=0.10)
    fig.savefig(FIGURES_DIR / "fig_rq1_success_at_k.png", dpi=260, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


def plot_marginal_gain(pinch_gpt: list[float], pinch_minimax: list[float], skills_gpt: list[float], skills_minimax: list[float]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 4.6), sharey=True)
    xs = list(range(1, 7))
    width = 0.38

    panels = [
        ("PinchBench-23", pinch_gpt, pinch_minimax),
        ("SkillsBench-32", skills_gpt, skills_minimax),
    ]
    for ax, (title, gpt, minimax) in zip(axes, panels):
        ax.bar([x - width / 2 for x in xs], minimax, width=width, color="#2c7fb8", alpha=0.9, label="MiniMax-M2.5")
        ax.bar([x + width / 2 for x in xs], gpt, width=width, color="#c73b2a", alpha=0.85, label="GPT-5.3-Codex")
        ax.set_title(title)
        ax.set_xlabel("Attempt")
        ax.set_ylabel("Marginal success gain")
        ax.set_xticks(xs)
        ax.set_ylim(0, 0.47)
        ax.grid(axis="y", alpha=0.25, linewidth=1.0)
        ax.tick_params(length=4, width=1.1)
        ax.legend(frameon=False, loc="upper right")

    fig.subplots_adjust(left=0.07, right=0.995, top=0.90, bottom=0.16, wspace=0.10)
    fig.savefig(FIGURES_DIR / "fig_rq1_marginal_gain_by_attempt.png", dpi=260, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


def main() -> None:
    pinch_minimax_tasks = pick_tasks(load_json(PINCHBENCH_MINIMAX))
    pinch_gpt_tasks = pick_tasks(load_json(PINCHBENCH_GPT))
    skills_minimax_tasks = pick_tasks(load_json(SKILLSBENCH_MINIMAX), SHARED_SKILLSBENCH_TASKS)
    skills_gpt_tasks = pick_tasks(load_json(SKILLSBENCH_GPT), SHARED_SKILLSBENCH_TASKS)

    pinch_gpt_curve = success_curve(pinch_gpt_tasks)
    pinch_minimax_curve = success_curve(pinch_minimax_tasks)
    skills_gpt_curve = success_curve(skills_gpt_tasks)
    skills_minimax_curve = success_curve(skills_minimax_tasks)

    plot_success_at_k(
        pinch_gpt_curve,
        pinch_minimax_curve,
        skills_gpt_curve,
        skills_minimax_curve,
    )
    plot_marginal_gain(
        marginal_gain(pinch_gpt_curve),
        marginal_gain(pinch_minimax_curve),
        marginal_gain(skills_gpt_curve),
        marginal_gain(skills_minimax_curve),
    )


if __name__ == "__main__":
    main()
