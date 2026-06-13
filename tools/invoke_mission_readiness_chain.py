"""Invoke mission-readiness Intel chain preset and print chain result."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.server.briefing_prompts import BRIEFING_PROMPT_LIBRARY

BASE = "http://127.0.0.1:9621"
TIMEOUT_S = 7200.0


def _mission_prompt() -> str:
    entry = next(
        item
        for item in BRIEFING_PROMPT_LIBRARY
        if item.get("slice_id") == "mission-readiness"
    )
    return str(entry["prompt"])


def main() -> int:
    payload = {
        "preset": "mission-readiness",
        "name": "mission-readiness-chain",
        "prompt": _mission_prompt(),
        "user_addendum": "",
    }
    print("POST /api/ui/skill-chains/invoke", flush=True)
    print(json.dumps({"preset": payload["preset"], "prompt_chars": len(payload["prompt"])}, indent=2), flush=True)
    with httpx.Client(timeout=TIMEOUT_S) as client:
        response = client.post(f"{BASE}/api/ui/skill-chains/invoke", json=payload)
        print("status:", response.status_code, flush=True)
        if response.status_code >= 400:
            print(response.text, flush=True)
            return 1
        body = response.json()
        print(json.dumps(body, indent=2)[:12000], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())