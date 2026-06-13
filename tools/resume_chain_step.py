"""Resume a skill chain from a given step."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:9621"
TIMEOUT_S = 7200.0


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: resume_chain_step.py <chain_id> <from_step_id>", file=sys.stderr)
        return 2
    chain_id = sys.argv[1]
    from_step_id = sys.argv[2]
    with httpx.Client(timeout=TIMEOUT_S) as client:
        response = client.post(
            f"{BASE}/api/ui/skill-chains/{chain_id}/resume",
            json={"from_step_id": from_step_id},
        )
    print("status:", response.status_code)
    if response.status_code >= 400:
        print(response.text)
        return 1
    body = response.json()
    print("chain_status:", body.get("chain", {}).get("status"))
    out = ROOT / "rag_storage" / "mcpp_rfp" / f"chain_resume_{from_step_id}.txt"
    out.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())