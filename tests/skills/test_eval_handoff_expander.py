"""Tests for eval handoff expander grounding."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.eval_handoff_expander import expansion_satisfied, prune_ungrounded_crosswalk_rows


def _write_eval_entities(workspace: Path, names: list[str]) -> None:
    records = [
        {"entity_type": "evaluation_factor", "entity_name": name} for name in names
    ]
    (workspace / "vdb_entities.json").write_text(
        json.dumps({"data": records}),
        encoding="utf-8",
    )


def test_expansion_not_satisfied_when_crosswalk_empty_despite_claim_gaps(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_eval_entities(workspace, ["Factor 1 Management", "Factor 2 Technical"])

    payload = {
        "eval_crosswalk": [],
        "claim_gaps": [
            "Factor 1 Management — no grounded chunk evidence after batch retrieval",
            "Factor 2 Technical — no grounded chunk evidence after batch retrieval",
        ],
    }
    assert expansion_satisfied(workspace_dir=workspace, payload=payload) is False


def test_prune_ungrounded_crosswalk_drops_invented_factors(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_eval_entities(workspace, ["Factor 1 Management Approach", "Factor 2 Technical"])

    payload = {
        "eval_crosswalk": [
            {
                "evaluation_factor": "Factor 1 Management Approach",
                "readiness_link": "x" * 60,
                "proof_expected": "y" * 30,
                "source_chunk_ids": ["chunk-real-1"],
            },
            {
                "evaluation_factor": "capset shorthand",
                "readiness_link": "x" * 60,
                "proof_expected": "y" * 30,
                "source_chunk_ids": ["chunk-real-1"],
            },
            {
                "evaluation_factor": "Factor 2 Technical",
                "readiness_link": "x" * 60,
                "proof_expected": "y" * 30,
                "source_chunk_ids": ["chunk-invented"],
            },
        ],
        "claim_gaps": [],
    }
    scratchpad = "Evidence chunk-real-1 discusses management staffing."

    pruned = prune_ungrounded_crosswalk_rows(
        payload,
        scratchpad=scratchpad,
        workspace_dir=workspace,
    )
    factors = [
        str(row.get("evaluation_factor") or "")
        for row in pruned.get("eval_crosswalk") or []
    ]
    assert factors == ["Factor 1 Management Approach"]
    gaps = pruned.get("claim_gaps") or []
    assert any("invented factor" in str(gap) for gap in gaps)
    assert any("ungrounded row" in str(gap) for gap in gaps)