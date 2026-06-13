"""Integration gate: real handoffs → merge → filled eval crosswalk."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.skills.mission_readiness_merge import merge_handoff_payloads, normalize_eval_crosswalk_row


def _handoff_root() -> Path:
    return Path(__file__).resolve().parents[2] / "rag_storage/mcpp_rfp/skill_runs"


def test_merge_real_eval_handoff_fills_readiness_links() -> None:
    eval_path = (
        _handoff_root()
        / "readiness-frame-eval"
        / "20260613_012727_build_the_mission_readiness_fram"
        / "artifacts/eval_handoff.json"
    )
    if not eval_path.is_file():
        pytest.skip("eval handoff fixture missing")

    eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
    merged = merge_handoff_payloads({"eval": eval_data})
    rows = merged.get("eval_crosswalk") or []
    assert len(rows) >= 10
    filled = [
        row
        for row in rows
        if isinstance(row, dict) and len(str(row.get("readiness_link") or "")) >= 40
    ]
    assert len(filled) == len(rows)


def test_normalize_never_returns_empty_readiness_when_crosswalk_present() -> None:
    row = normalize_eval_crosswalk_row(
        {
            "evaluation_factor": "Factor 2 Technical",
            "readiness_link": "",
            "proof_expected": "",
            "evaluation_crosswalk": "Evaluators assess technical methodology depth for readiness sustainment across all PWS task areas.",
            "source_chunk_ids": ["tb-1234567890abcdef"],
        }
    )
    assert len(row["readiness_link"]) >= 40
    assert row["proof_expected"]