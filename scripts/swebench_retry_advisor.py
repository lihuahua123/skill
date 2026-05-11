#!/usr/bin/env python3

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import anthropic
except ImportError:  # pragma: no cover - optional dependency in some envs
    anthropic = None


DEFAULT_MINIMAX_BASE_URL = "https://api.minimaxi.com/anthropic"
DEFAULT_MINIMAX_MODEL = "MiniMax-M2.7"
DEFAULT_API_KEY_FILE = Path("/data/lirui/skill_study/.minimaxapikey")


def _normalize_model_name(model_name: str) -> str:
    if "/" not in model_name:
        return model_name
    return model_name.split("/", 1)[1]


def _load_api_key(api_key_file: str | os.PathLike[str] | None = None) -> str | None:
    env_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if env_key and not env_key.startswith("dummy-"):
        return env_key
    path = Path(api_key_file) if api_key_file else DEFAULT_API_KEY_FILE
    if not path.is_file():
        return None
    key = path.read_text(encoding="utf-8").strip()
    return key or None


def _extract_text(message: Any) -> str:
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(str(text).strip())
    return "\n".join(part for part in parts if part).strip()


def _build_user_prompt(
    *,
    instance: dict[str, Any],
    attempt_number: int,
    eval_result: dict[str, Any],
    summary: dict[str, Any],
) -> str:
    failed_tests = summary.get("failed_tests") or []
    failed_tests_block = "\n".join(f"- {name}" for name in failed_tests[:8]) or "- none"
    notes = str(summary.get("notes") or "No evaluation notes.")
    return (
        f"Instance: {instance.get('instance_id', '')}\n"
        f"Repository: {instance.get('repo', '')}\n"
        f"Attempt completed: {attempt_number}\n"
        f"Resolved: {'yes' if bool(eval_result.get('resolved')) else 'no'}\n\n"
        f"Failed tests:\n{failed_tests_block}\n\n"
        f"Evaluation notes:\n{notes}\n"
    )


def request_retry_advice(
    *,
    instance: dict[str, Any],
    attempt_number: int,
    eval_result: dict[str, Any],
    summary: dict[str, Any],
    enabled: bool = False,
    model: str = DEFAULT_MINIMAX_MODEL,
    max_tokens: int = 180,
    api_key_file: str | os.PathLike[str] | None = None,
    base_url: str | None = None,
) -> str | None:
    if not enabled or anthropic is None:
        return None
    api_key = _load_api_key(api_key_file)
    if not api_key:
        return None
    try:
        client = anthropic.Anthropic(
            api_key=api_key,
            base_url=base_url or os.environ.get("MINIMAX_ANTHROPIC_BASE_URL") or DEFAULT_MINIMAX_BASE_URL,
        )
        message = client.messages.create(
            model=_normalize_model_name(model),
            max_tokens=max_tokens,
            temperature=0,
            system=(
                "You are a SWE-bench retry triage assistant. Infer why the previous patch direction likely failed "
                "and suggest a higher-level direction change. Do not provide code, file paths, exact patch text, "
                "or exact expected output strings. Reply in at most three short bullet points."
            ),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": _build_user_prompt(
                                instance=instance,
                                attempt_number=attempt_number,
                                eval_result=eval_result,
                                summary=summary,
                            ),
                        }
                    ],
                }
            ],
        )
    except Exception:
        return None
    advice = _extract_text(message)
    if not advice:
        return None
    return advice[:1200].strip()
