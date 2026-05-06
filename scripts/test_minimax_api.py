#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

import anthropic


API_KEY_PATH = Path("/data/lirui/skill_study/.minimaxapikey")
BASE_URL = "https://api.minimaxi.com/anthropic"
MODEL = "MiniMax-M2.7"


def load_api_key() -> str:
    key = API_KEY_PATH.read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError(f"Empty API key file: {API_KEY_PATH}")
    return key


def main() -> int:
    try:
        api_key = load_api_key()
        client = anthropic.Anthropic(api_key=api_key, base_url=BASE_URL)
        message = client.messages.create(
            model=MODEL,
            max_tokens=128,
            system="You are a helpful assistant.",
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "Reply with exactly: ok"}],
                }
            ],
        )
    except Exception as exc:
        print(f"MiniMax API test failed: {exc}", file=sys.stderr)
        return 1

    print("MiniMax API test succeeded.")
    for block in message.content:
        if block.type == "thinking":
            print("Thinking:")
            print(block.thinking)
        elif block.type == "text":
            print("Text:")
            print(block.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
