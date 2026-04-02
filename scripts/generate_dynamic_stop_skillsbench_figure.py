#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt


ROOT = Path("/root")
FIGURES_DIR = ROOT / "neurips_2026_template/figures"
MINIMAX_PATH = ROOT / "skill/results/rq1/skillsbench__minimax-cn-MiniMax-M2-5__merged_with_token_patch.json"
GPT_PATH = ROOT / "skill/results/rq1/skillsbench__openai-gpt-5-3-codex__2026-03-28__19-58-04.json"
PRICING_PATH = ROOT / "skill/analysis/rq1/token_pricing_cny_per_mtoken.json"
SHARED_TASKS = [
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
        "legend.fontsize": 13,
        "axes.linewidth": 1.2,
    }
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def cut_on_flat_delta(task: dict) -> list[dict]:
    kept: list[dict] = []
    for attempt in task.get("attempts", []) or []:
        kept.append(attempt)
        delta = attempt.get("score_delta")
        if delta is not None and float(delta) == 0.0:
            break
    return kept


def dynamic_first_success(task: dict) -> int | None:
    first_success_attempt = task.get("first_success_attempt")
    if first_success_attempt is None:
        return None
    cutoff = max((int(a.get("attempt") or 0) for a in cut_on_flat_delta(task)), default=0)
    return int(first_success_attempt) if int(first_success_attempt) <= cutoff else None


def attempt_cost_cny(attempt: dict, prices: dict[str, float]) -> float:
    usage = ((attempt.get("execution") or {}).get("usage") or attempt.get("usage") or {})
    return (
        float(usage.get("input_tokens") or 0) / 1_000_000 * prices["input_tokens"]
        + float(usage.get("output_tokens") or 0) / 1_000_000 * prices["output_tokens"]
        + float(usage.get("cache_read_tokens") or 0) / 1_000_000 * prices["cache_read_tokens"]
        + float(usage.get("cache_write_tokens") or 0) / 1_000_000 * prices["cache_write_tokens"]
    )


def success_curve(tasks: list[dict], mode: str) -> list[float]:
    values: list[float] = []
    for k in range(1, 7):
        successes = 0
        for task in tasks:
            if mode == "standard":
                fsa = task.get("first_success_attempt")
            else:
                fsa = dynamic_first_success(task)
            if fsa is not None and int(fsa) <= k:
                successes += 1
        values.append(successes / len(tasks))
    return values


def summary(tasks: list[dict], prices: dict[str, float], mode: str) -> dict[str, float]:
    first_success = 0
    final_success = 0
    first_cost = 0.0
    total_cost = 0.0
    for task in tasks:
        attempts = task.get("attempts", []) or []
        kept = attempts if mode == "standard" else cut_on_flat_delta(task)
        if attempts:
            first_cost += attempt_cost_cny(attempts[0], prices)
        total_cost += sum(attempt_cost_cny(a, prices) for a in kept)
        fsa = task.get("first_success_attempt") if mode == "standard" else dynamic_first_success(task)
        if fsa == 1:
            first_success += 1
        if fsa is not None:
            final_success += 1
    n = len(tasks)
    return {
        "first_success_rate": first_success / n,
        "final_success_rate": final_success / n,
        "attempt1_mean_cost_cny": first_cost / n,
        "total_mean_cost_cny": total_cost / n,
    }


def main() -> None:
    pricing = load_json(PRICING_PATH)
    minimax_tasks = [t for t in load_json(MINIMAX_PATH).get("tasks", []) if t.get("task_id") in set(SHARED_TASKS)]
    gpt_tasks = load_json(GPT_PATH).get("tasks", [])
    payloads = {
        "MiniMax-M2.5": minimax_tasks,
        "GPT-5.3-Codex": gpt_tasks,
    }
    colors = {"MiniMax-M2.5": "#2c7fb8", "GPT-5.3-Codex": "#c73b2a"}
    markers = {"standard": "o", "dynamic": "s"}
    linestyles = {"standard": "-", "dynamic": "--"}
    labels = {"standard": "Standard", "dynamic": "Dynamic stop"}

    fig, axes = plt.subplots(1, 2, figsize=(13.2, 4.8))
    xs = list(range(1, 7))

    for model, tasks in payloads.items():
        for mode in ["standard", "dynamic"]:
            curve = success_curve(tasks, mode)
            axes[0].plot(
                xs,
                curve,
                marker=markers[mode],
                linestyle=linestyles[mode],
                linewidth=2.6,
                markersize=8,
                color=colors[model],
                label=f"{model} ({labels[mode]})",
            )
            stats = summary(tasks, pricing[model], mode)
            axes[1].scatter(
                stats["total_mean_cost_cny"],
                stats["final_success_rate"],
                s=120,
                marker=markers[mode],
                color=colors[model],
                label=f"{model} ({labels[mode]})",
            )

        standard_stats = summary(tasks, pricing[model], "standard")
        dynamic_stats = summary(tasks, pricing[model], "dynamic")
        axes[1].annotate(
            "",
            xy=(dynamic_stats["total_mean_cost_cny"], dynamic_stats["final_success_rate"]),
            xytext=(standard_stats["total_mean_cost_cny"], standard_stats["final_success_rate"]),
            arrowprops=dict(arrowstyle="->", color=colors[model], lw=2.0, alpha=0.85),
        )

    axes[0].set_title("SkillsBench-32: success@k under dynamic stop")
    axes[0].set_xlabel("Attempt")
    axes[0].set_ylabel("Cumulative success rate")
    axes[0].set_xticks(xs)
    axes[0].set_ylim(0.0, 0.45)
    axes[0].grid(alpha=0.25)

    axes[1].set_title("SkillsBench-32: cost-success shift")
    axes[1].set_xlabel("Total mean cost (CNY/task)")
    axes[1].set_ylabel("Final success rate")
    axes[1].set_xlim(0.75, 1.55)
    axes[1].set_ylim(0.15, 0.43)
    axes[1].grid(alpha=0.25)

    handles, labels_out = axes[0].get_legend_handles_labels()
    uniq = dict(zip(labels_out, handles))
    axes[0].legend(uniq.values(), uniq.keys(), frameon=False, loc="lower right")
    axes[1].legend(uniq.values(), uniq.keys(), frameon=False, loc="lower left")

    fig.subplots_adjust(left=0.07, right=0.995, top=0.90, bottom=0.16, wspace=0.18)
    fig.savefig(FIGURES_DIR / "fig_dynamic_stop_skillsbench.png", dpi=260, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


if __name__ == "__main__":
    main()
