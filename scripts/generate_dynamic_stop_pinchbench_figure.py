#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt


ROOT = Path("/root")
FIGURES_DIR = ROOT / "neurips_2026_template/figures"
MINIMAX_PATH = ROOT / "skill/results/rq1/pinchbench_minimax-cn-MiniMax-M2-5__merged.json"
GPT_PATH = ROOT / "skill/results/rq1/pinchbench_autodl-gpt-5-3-codex.json"
PRICING_PATH = ROOT / "skill/analysis/rq1/token_pricing_cny_per_mtoken.json"

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


def cut_on_repeated_score(task: dict) -> list[dict]:
    kept = []
    prev_score = None
    for attempt in task.get("attempts", []) or []:
        score = (attempt.get("grading") or {}).get("score")
        kept.append(attempt)
        if prev_score is not None and score == prev_score:
            break
        prev_score = score
    return kept


def attempt_cost_cny(attempt: dict, prices: dict[str, float]) -> float:
    usage = ((attempt.get("execution") or {}).get("usage") or attempt.get("usage") or {})
    return (
        float(usage.get("input_tokens") or 0) / 1_000_000 * prices["input_tokens"]
        + float(usage.get("output_tokens") or 0) / 1_000_000 * prices["output_tokens"]
        + float(usage.get("cache_read_tokens") or 0) / 1_000_000 * prices["cache_read_tokens"]
        + float(usage.get("cache_write_tokens") or 0) / 1_000_000 * prices["cache_write_tokens"]
    )


def success_curve(tasks: list[dict], mode: str, max_attempts: int = 6) -> list[float]:
    values: list[float] = []
    for k in range(1, max_attempts + 1):
        successes = 0
        for task in tasks:
            if mode == "standard":
                first_success_attempt = task.get("first_success_attempt")
                if first_success_attempt is not None and int(first_success_attempt) <= k:
                    successes += 1
                continue

            kept = cut_on_repeated_score(task)
            first_success_attempt = None
            for attempt in kept:
                grading = attempt.get("grading") or {}
                score = grading.get("score")
                max_score = grading.get("max_score")
                if score is not None and max_score is not None and float(max_score) > 0 and float(score) >= float(max_score):
                    first_success_attempt = int(attempt.get("attempt") or 0)
                    break
            if first_success_attempt is not None and first_success_attempt <= k:
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
        kept = attempts if mode == "standard" else cut_on_repeated_score(task)
        if attempts:
            first = attempts[0]
            first_cost += attempt_cost_cny(first, prices)
            grading = first.get("grading") or {}
            score = grading.get("score")
            max_score = grading.get("max_score")
            if score is not None and max_score is not None and float(max_score) > 0 and float(score) >= float(max_score):
                first_success += 1
        total_cost += sum(attempt_cost_cny(attempt, prices) for attempt in kept)

        success = False
        for attempt in kept:
            grading = attempt.get("grading") or {}
            score = grading.get("score")
            max_score = grading.get("max_score")
            if score is not None and max_score is not None and float(max_score) > 0 and float(score) >= float(max_score):
                success = True
                break
        if success:
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
    payloads = {
        "MiniMax-M2.5": load_json(MINIMAX_PATH),
        "GPT-5.3-Codex": load_json(GPT_PATH),
    }
    colors = {"MiniMax-M2.5": "#2c7fb8", "GPT-5.3-Codex": "#c73b2a"}
    markers = {"standard": "o", "dynamic": "s"}
    linestyles = {"standard": "-", "dynamic": "--"}
    labels = {"standard": "Standard", "dynamic": "Dynamic stop"}

    fig, axes = plt.subplots(1, 2, figsize=(13.2, 4.8))
    xs = list(range(1, 7))

    for model, payload in payloads.items():
        tasks = payload.get("tasks", []) or []
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

    axes[0].set_title("PinchBench: success@k under dynamic stop")
    axes[0].set_xlabel("Attempt")
    axes[0].set_ylabel("Cumulative success rate")
    axes[0].set_xticks(xs)
    axes[0].set_ylim(0.25, 0.8)
    axes[0].grid(alpha=0.25)

    axes[1].set_title("PinchBench: cost-success shift")
    axes[1].set_xlabel("Total mean cost (CNY/task)")
    axes[1].set_ylabel("Final success rate")
    axes[1].set_xlim(0.18, 0.45)
    axes[1].set_ylim(0.30, 0.78)
    axes[1].grid(alpha=0.25)

    handles, labels_out = axes[0].get_legend_handles_labels()
    uniq = dict(zip(labels_out, handles))
    axes[0].legend(uniq.values(), uniq.keys(), frameon=False, loc="lower right")
    axes[1].legend(uniq.values(), uniq.keys(), frameon=False, loc="lower right")

    fig.subplots_adjust(left=0.07, right=0.995, top=0.90, bottom=0.16, wspace=0.18)
    fig.savefig(FIGURES_DIR / "fig_dynamic_stop_pinchbench.png", dpi=260, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


if __name__ == "__main__":
    main()
