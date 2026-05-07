#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from datasets import load_dataset

REPO_ROOT = Path(__file__).resolve().parents[1]
MINISWEAGENT_SRC = REPO_ROOT.parent / "EET" / "mini-swe-agent" / "src"
os.environ.setdefault("XDG_CONFIG_HOME", "/tmp/mini_sweagent_config")
sys.path.insert(0, str(MINISWEAGENT_SRC))

from minisweagent.agents.default import DefaultAgent
from minisweagent.agents.experience_retrieval import ExperienceRetrievalAgent
from minisweagent.models import get_model
from minisweagent.models.test_models import DeterministicModel
from minisweagent.run.extra.swebench import get_sb_environment
from minisweagent.run.utils.save import save_traj


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run single-attempt SWE-bench evaluation with mini-swe-agent."
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--dataset-path", required=True, type=Path)
    parser.add_argument("--dataset-split", default="test")
    parser.add_argument("--eval-dataset-name", default="")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--swebench-instance-id", default="")
    parser.add_argument("--max-task-attempts", type=int, default=1)
    parser.add_argument("--swebench-agent-backend", choices=("plain-mini", "eet-mini"), default="plain-mini")
    parser.add_argument("--swebench-max-workers", type=int, default=1)
    parser.add_argument("--runner-python", required=True)
    parser.add_argument("--model-class", default="")
    parser.add_argument("--model-output", action="append", default=[])
    parser.add_argument("--skip-evaluation", action="store_true")
    return parser.parse_args()


def load_instances(dataset_path: Path, split: str) -> list[dict[str, Any]]:
    if dataset_path.suffix == ".parquet":
        dataset = load_dataset("parquet", data_files=str(dataset_path), split="train")
    else:
        dataset = load_dataset(str(dataset_path), split=split)
    return [dict(item) for item in dataset]


def filter_instances(
    instances: list[dict[str, Any]], instance_ids_arg: str
) -> list[dict[str, Any]]:
    if not instance_ids_arg:
        return instances
    wanted = {item.strip() for item in instance_ids_arg.split(",") if item.strip()}
    return [instance for instance in instances if instance["instance_id"] in wanted]


def config_path_for_backend(backend: str) -> Path:
    config_root = MINISWEAGENT_SRC / "minisweagent" / "config" / "extra"
    if backend == "plain-mini":
        return config_root / "swebench.yaml"
    return config_root / "swebench_experience.yaml"


def load_agent_config(backend: str, model_name: str) -> dict[str, Any]:
    config = yaml.safe_load(config_path_for_backend(backend).read_text(encoding="utf-8"))
    config.setdefault("model", {})["model_name"] = model_name
    return config


def build_prediction(instance_id: str, model_name: str, patch: str) -> dict[str, Any]:
    return {
        instance_id: {
            "model_name_or_path": model_name,
            "instance_id": instance_id,
            "model_patch": patch,
        }
    }


def run_single_attempt(
    *,
    instance: dict[str, Any],
    model_name: str,
    backend: str,
    config_template: dict[str, Any],
    attempt_dir: Path,
) -> tuple[Path, Path, float]:
    instance_id = instance["instance_id"]
    config = copy.deepcopy(config_template)
    if config["model"].get("model_class") == "deterministic":
        deterministic_model_config = dict(config["model"])
        deterministic_model_config.pop("model_class", None)
        model = DeterministicModel(**deterministic_model_config)
    else:
        model = get_model(config=config["model"])
    env = get_sb_environment(config, instance)
    agent_config = config.get("agent", {})
    task = instance["problem_statement"]

    started_at = time.time()
    if backend == "plain-mini":
        agent = DefaultAgent(model, env, **agent_config)
        exit_status, result = agent.run(task)
    else:
        agent = ExperienceRetrievalAgent(model, env, **agent_config)
        exit_status, result = agent.run(task, issue_id=instance_id)
    finished_at = time.time()

    traj_path = attempt_dir / "traj.json"
    save_traj(
        agent,
        traj_path,
        exit_status=exit_status,
        result=result,
        instance_id=instance_id,
        print_path=False,
    )

    prediction_path = attempt_dir / "prediction.json"
    prediction_path.write_text(
        json.dumps(build_prediction(instance_id, model_name, result), indent=2),
        encoding="utf-8",
    )
    return traj_path, prediction_path, finished_at - started_at


def run_evaluation(
    *,
    runner_python: str,
    eval_dataset_name: str,
    prediction_path: Path,
    model_name: str,
    run_id: str,
    split: str,
    instance_id: str,
    max_workers: int,
    output_root: Path,
    attempt_dir: Path,
) -> tuple[Path, float]:
    runner_python = str(Path(runner_python).absolute())
    eval_started_at = time.time()
    subprocess.run(
        [
            runner_python,
            "-m",
            "swebench.harness.run_evaluation",
            "--dataset_name",
            eval_dataset_name,
            "--predictions_path",
            str(prediction_path),
            "--max_workers",
            str(max_workers),
            "--run_id",
            run_id,
        ],
        check=True,
        cwd=str(output_root),
    )
    eval_finished_at = time.time()

    model_log_name = model_name.replace("/", "__")
    report_path = (
        output_root / "logs" / "run_evaluation" / run_id / model_log_name / instance_id / "report.json"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    test_output_path = (
        output_root / "logs" / "run_evaluation" / run_id / model_log_name / instance_id / "test_output.txt"
    )

    eval_result_path = attempt_dir / "eval_result.json"
    eval_result_path.write_text(
        json.dumps(
            {
                "instance_id": instance_id,
                "run_id": run_id,
                "split": split,
                "resolved": bool(report[instance_id]["resolved"]),
                "report_path": str(report_path),
                "test_output_path": str(test_output_path),
                "evaluation_time_seconds": eval_finished_at - eval_started_at,
                "report": report,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return eval_result_path, eval_finished_at - eval_started_at


def main() -> None:
    args = parse_args()
    if args.max_task_attempts != 1:
        raise ValueError("SWE-bench minimal adapter currently supports only --max-task-attempts 1")

    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(output_root / ".hf_cache"))

    instances = filter_instances(load_instances(args.dataset_path.resolve(), args.dataset_split), args.swebench_instance_id)
    config_template = load_agent_config(args.swebench_agent_backend, args.model)
    if args.model_class:
        config_template.setdefault("model", {})["model_class"] = args.model_class
    if args.model_output:
        config_template.setdefault("model", {})["outputs"] = args.model_output
    if args.model_class == "deterministic":
        config_template["model"].pop("model_kwargs", None)
        config_template["model"].pop("set_cache_control", None)

    for instance in instances:
        instance_id = instance["instance_id"]
        instance_root = output_root / instance_id
        attempt_dir = instance_root / "attempt_1"
        attempt_dir.mkdir(parents=True, exist_ok=True)

        traj_path, prediction_path, agent_time = run_single_attempt(
            instance=instance,
            model_name=args.model,
            backend=args.swebench_agent_backend,
            config_template=config_template,
            attempt_dir=attempt_dir,
        )

        if args.skip_evaluation:
            eval_result_path = attempt_dir / "eval_result.json"
            eval_result_path.write_text(
                json.dumps(
                    {
                        "instance_id": instance_id,
                        "run_id": "",
                        "split": args.dataset_split,
                        "resolved": False,
                        "report_path": "",
                        "test_output_path": "",
                        "evaluation_time_seconds": 0.0,
                        "report": {},
                        "skipped": True,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            evaluation_time = 0.0
        else:
            if not args.eval_dataset_name:
                raise ValueError("--eval-dataset-name is required unless --skip-evaluation is set")
            eval_run_id = f"{args.run_id}__{instance_id}__attempt_1"
            eval_result_path, evaluation_time = run_evaluation(
                runner_python=args.runner_python,
                eval_dataset_name=args.eval_dataset_name,
                prediction_path=prediction_path,
                model_name=args.model,
                run_id=eval_run_id,
                split=args.dataset_split,
                instance_id=instance_id,
                max_workers=args.swebench_max_workers,
                output_root=output_root,
                attempt_dir=attempt_dir,
            )

        task_summary = {
            "task_id": instance_id,
            "attempt_count": 1,
            "attempts": [
                {
                    "attempt": 1,
                    "traj_json": str(traj_path),
                    "prediction_json": str(prediction_path),
                    "eval_json": str(eval_result_path),
                    "agent_time_seconds": agent_time,
                    "evaluation_time_seconds": evaluation_time,
                }
            ],
        }
        (instance_root / "task_summary.json").write_text(
            json.dumps(task_summary, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
