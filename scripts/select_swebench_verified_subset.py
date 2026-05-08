#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import random
from collections import Counter, defaultdict
from pathlib import Path

from datasets import load_dataset

FULL_DATASET_COUNTS = {
    "astropy/astropy": 22,
    "django/django": 231,
    "matplotlib/matplotlib": 34,
    "mwaskom/seaborn": 2,
    "pallets/flask": 1,
    "psf/requests": 8,
    "pydata/xarray": 22,
    "pylint-dev/pylint": 10,
    "pytest-dev/pytest": 19,
    "scikit-learn/scikit-learn": 32,
    "sphinx-doc/sphinx": 44,
    "sympy/sympy": 75,
}

SUBSET_COUNTS = {
    "astropy/astropy": 4,
    "django/django": 47,
    "matplotlib/matplotlib": 7,
    "mwaskom/seaborn": 0,
    "pallets/flask": 0,
    "psf/requests": 2,
    "pydata/xarray": 4,
    "pylint-dev/pylint": 2,
    "pytest-dev/pytest": 4,
    "scikit-learn/scikit-learn": 6,
    "sphinx-doc/sphinx": 9,
    "sympy/sympy": 15,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a reproducible 100-task SWE-bench Verified subset that "
            "matches the repository distribution from Gao and Peng (2026), Table 1."
        )
    )
    parser.add_argument("--dataset-path", required=True, type=Path)
    parser.add_argument("--dataset-split", default="test")
    parser.add_argument("--seed", type=int, default=251016786)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary-output", type=Path)
    return parser.parse_args()


def load_instances(dataset_path: Path, split: str) -> list[dict]:
    dataset_path = dataset_path.resolve()
    if dataset_path.suffix == ".parquet":
        dataset = load_dataset("parquet", data_files=str(dataset_path), split="train")
    else:
        dataset = load_dataset(str(dataset_path), split=split)
    return [dict(item) for item in dataset]


def select_subset(instances: list[dict], seed: int) -> tuple[list[str], dict[str, dict[str, int]]]:
    by_repo: dict[str, list[str]] = defaultdict(list)
    for instance in instances:
        by_repo[str(instance["repo"])].append(str(instance["instance_id"]))

    available_counts = Counter({repo: len(ids) for repo, ids in by_repo.items()})
    if Counter(FULL_DATASET_COUNTS) != available_counts:
        raise ValueError(
            "Dataset repository distribution does not match the expected SWE-bench Verified counts: "
            f"expected={dict(sorted(FULL_DATASET_COUNTS.items()))}, "
            f"actual={dict(sorted(available_counts.items()))}"
        )

    rng = random.Random(seed)
    selected: list[str] = []
    repo_summary: dict[str, dict[str, int]] = {}
    for repo in sorted(SUBSET_COUNTS):
        target_count = SUBSET_COUNTS[repo]
        repo_ids = sorted(by_repo[repo])
        if target_count > len(repo_ids):
            raise ValueError(f"Requested {target_count} tasks from {repo}, but only found {len(repo_ids)}")
        chosen = sorted(rng.sample(repo_ids, target_count)) if target_count else []
        selected.extend(chosen)
        repo_summary[repo] = {
            "available_count": len(repo_ids),
            "selected_count": len(chosen),
        }
    return selected, repo_summary


def main() -> None:
    args = parse_args()
    os.environ.setdefault("HF_HOME", "/tmp/hf_cache")
    os.environ.setdefault("XDG_CACHE_HOME", "/tmp/xdg_cache")

    selected, repo_summary = select_subset(
        load_instances(args.dataset_path, args.dataset_split),
        args.seed,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(selected) + "\n", encoding="utf-8")

    summary_output = args.summary_output
    if summary_output is not None:
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary_output.write_text(
            json.dumps(
                {
                    "dataset_path": str(args.dataset_path.resolve()),
                    "dataset_split": args.dataset_split,
                    "seed": args.seed,
                    "total_selected": len(selected),
                    "repo_summary": repo_summary,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
