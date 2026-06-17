from __future__ import annotations

import json
from pathlib import Path

from tools.snapshot_workspace_kg import (
    _compare_workspaces,
    _entity_name_index,
    _explosion_attribution,
    _parse_relationship_first_token,
    build_workspace_snapshot,
)


def test_parse_relationship_first_token_from_content():
    record = {
        "content": "CONTAINS PHASE_OF\tSource\nTarget\nDescription",
    }
    assert _parse_relationship_first_token(record) == "CONTAINS"


def test_parse_relationship_first_token_from_keywords_field():
    record = {"keywords": "GUIDES, compliance mapping"}
    assert _parse_relationship_first_token(record) == "GUIDES"


def test_explosion_attribution_structural_driver():
    result = _explosion_attribution(
        chunk_ratio=1.88,
        entity_ratio=1.45,
        net_new_share=0.35,
        shared_share=0.65,
    )
    assert result["structural_chunk_driver"] is True
    assert result["per_chunk_yield_ratio"] < 1.0


def test_compare_workspaces_overlap():
    baseline = _entity_name_index(
        [
            {"entity_name": "Factor 1", "description": "alpha"},
            {"entity_name": "CDRL A001", "description": "beta"},
        ]
    )
    candidate = _entity_name_index(
        [
            {"entity_name": "Factor 1", "description": "alpha extended text"},
            {"entity_name": "New Requirement", "description": "gamma"},
        ]
    )
    comparison = _compare_workspaces(baseline, candidate)
    assert comparison["shared_entity_names"] == 1
    assert comparison["only_in_candidate"] == 1
    assert comparison["only_in_baseline"] == 1


def test_build_workspace_snapshot_mcpp_rfp():
    root = Path(__file__).resolve().parents[1]
    workspace = root / "rag_storage" / "mcpp_rfp"
    if not workspace.exists():
        return
    snapshot = build_workspace_snapshot("mcpp_rfp")
    assert snapshot["chunk_count"] > 0
    assert snapshot["total_entities_vdb"] > 0
    assert "orphan_rate_vdb" in snapshot
    assert snapshot["rogue_first_token_share"] >= 0


def test_build_workspace_snapshot_compare(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    if not (root / "rag_storage" / "mcpp_rfp_t2").exists():
        return
    snapshot = build_workspace_snapshot("mcpp_rfp_t2", compare_with="mcpp_rfp")
    assert snapshot["comparison_with"] == "mcpp_rfp"
    assert "explosion_attribution" in snapshot["comparison"]
    out = tmp_path / "snap.json"
    out.write_text(json.dumps(snapshot), encoding="utf-8")
    assert out.exists()