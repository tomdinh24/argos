"""Smoke-test the Anthropic and OpenAI API keys.

Loads .env from the project root, fires one trivial call to each provider,
and reports OK/FAIL. Used once after `.env` setup to confirm credentials
work before building anything that depends on them.

Run: .venv/bin/python scripts/smoke_test_keys.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def check_anthropic() -> tuple[bool, str]:
    try:
        from anthropic import Anthropic
        client = Anthropic()
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": "say 'ok' and nothing else"}],
        )
        text = resp.content[0].text.strip()
        return True, f"Anthropic ({resp.model}): {text!r}"
    except Exception as e:
        return False, f"Anthropic FAILED: {type(e).__name__}: {e}"


def check_openai() -> tuple[bool, str]:
    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=10,
            messages=[{"role": "user", "content": "say 'ok' and nothing else"}],
        )
        text = (resp.choices[0].message.content or "").strip()
        return True, f"OpenAI ({resp.model}): {text!r}"
    except Exception as e:
        return False, f"OpenAI FAILED: {type(e).__name__}: {e}"


def main() -> int:
    print("Smoke-testing API keys from .env\n")
    results = [check_anthropic(), check_openai()]
    for ok, msg in results:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {msg}")
    print()
    return 0 if all(ok for ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
