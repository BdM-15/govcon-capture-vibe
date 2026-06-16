"""Invoke one readiness-frame micro-skill solo (LangGraph step pipeline + assess)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.server.briefing_prompts import BRIEFING_PROMPT_LIBRARY
from src.skills.local_llm_admin import admin_llm_status
from src.skills.ensure_theseus_server import ensure_theseus_server_fresh
from src.skills.readiness_solo_invoke import (
    READINESS_SOLO_STEP_IDS,
    assess_readiness_solo_step,
    build_solo_invoke_http_payload,
    preflight_readiness_solo,
)

BASE = "http://127.0.0.1:9621"
TIMEOUT_S = 7200.0


def _mission_prompt() -> str:
    entry = next(
        item
        for item in BRIEFING_PROMPT_LIBRARY
        if item.get("slice_id") == "mission-readiness"
    )
    return str(entry["prompt"])


def _workspace_root() -> Path:
    from src.core import get_settings

    settings = get_settings()
    return ROOT / "rag_storage" / settings.workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "step_id",
        choices=sorted(READINESS_SOLO_STEP_IDS),
        help="Readiness chain step to run solo",
    )
    parser.add_argument("--prompt", default="", help="Override mission-readiness prompt")
    parser.add_argument("--user-addendum", default="", help="Optional Intel context")
    parser.add_argument("--assess-only", metavar="RUN_DIR", help="Assess existing run dir")
    parser.add_argument("--base-url", default=BASE, help="Theseus API base URL")
    parser.add_argument(
        "--skip-server-ensure",
        action="store_true",
        help="Do not restart server when code fingerprint is stale (not recommended)",
    )
    args = parser.parse_args(argv)

    if args.assess_only:
        run_dir = Path(args.assess_only)
        result = assess_readiness_solo_step(
            step_id=args.step_id,
            run_dir=run_dir,
            workspace_root=_workspace_root(),
        )
        print(json.dumps(result.__dict__, indent=2), flush=True)
        return 0 if result.passed else 1

    if not args.skip_server_ensure:
        ok, message = ensure_theseus_server_fresh(
            base_url=args.base_url,
            restart=not args.skip_server_ensure,
        )
        print(message, flush=True)
        if not ok:
            return 2

    preflight_error = preflight_readiness_solo(args.step_id)
    if preflight_error:
        print(preflight_error, flush=True)
        print(json.dumps({"admin_llm": admin_llm_status()}, indent=2), flush=True)
        return 2

    prompt = str(args.prompt or "").strip() or _mission_prompt()
    payload = build_solo_invoke_http_payload(
        args.step_id,
        prompt,
        user_addendum=args.user_addendum,
    )
    print("POST /api/ui/skill-chains/invoke", flush=True)
    print(json.dumps(payload, indent=2), flush=True)
    with httpx.Client(timeout=TIMEOUT_S) as client:
        response = client.post(f"{args.base_url}/api/ui/skill-chains/invoke", json=payload)
        print("status:", response.status_code, flush=True)
        if response.status_code >= 400:
            print(response.text, flush=True)
            return 1
        body = response.json()

    chain = body.get("chain") or {}
    steps = chain.get("steps") or {}
    step_run = steps.get(args.step_id) or {}
    run_dir = str(step_run.get("run_dir") or "").strip()
    if not run_dir:
        print(json.dumps(body, indent=2)[:12000], flush=True)
        print("error: step run_dir missing — cannot assess", flush=True)
        return 1

    result = assess_readiness_solo_step(
        step_id=args.step_id,
        run_dir=Path(run_dir),
        workspace_root=_workspace_root(),
        finish_reason="stop",
        warnings=list(step_run.get("warnings") or []),
    )
    print(json.dumps(result.__dict__, indent=2), flush=True)
    if step_run.get("status") not in {"completed", "partial"}:
        return 1
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())