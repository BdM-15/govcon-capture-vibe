"""Tests for readiness handoff Pydantic contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.skills.readiness_handoff_models import (
    EvalCrosswalkRow,
    EvalHandoff,
    TeaLeavesHandoff,
    WorkloadHandoff,
    validate_handoff_file,
    validate_handoff_payload,
)


def test_eval_crosswalk_row_from_legacy_maps_narrative() -> None:
    row = EvalCrosswalkRow.from_legacy(
        {
            "factor": "Factor 1 Management",
            "evaluation_crosswalk": "Program office evaluates organizational integration for readiness " * 3,
            "source_chunk_ids": ["tb-abc123", "section_m"],
        }
    )
    assert "organizational integration" in row.readiness_link.lower()
    assert row.source_chunk_ids == ["tb-abc123"]


def test_validate_handoff_payload_rejects_thin_eval_rows() -> None:
    with pytest.raises(ValidationError):
        validate_handoff_payload(
            "eval_handoff.json",
            {
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Factor 1",
                        "readiness_link": "short",
                        "proof_expected": "short",
                        "source_chunk_ids": [],
                    }
                ]
            },
        )


def test_validate_handoff_file_parses_fenced_json(tmp_path: Path) -> None:
    path = tmp_path / "eval_handoff.json"
    path.write_text(
        '```json\n{"eval_crosswalk": [], "claim_gaps": ["defer"]}\n```\n',
        encoding="utf-8",
    )
    model = validate_handoff_file(path)
    assert isinstance(model, EvalHandoff)
    assert model.claim_gaps == ["defer"]


def test_workload_handoff_accepts_flat_envelope() -> None:
    model = WorkloadHandoff.from_payload(
        {
            "readiness_outcome": "Mission-ready sustainment by FY27",
            "workload_enablers": [{"cluster": "PWS 3.1", "readiness_link": "x" * 40}],
            "claim_gaps": [],
        }
    )
    assert model.mission_readiness_frame["readiness_outcome"].startswith("Mission-ready")
    assert len(model.mission_readiness_frame["workload_enablers"]) == 1


def test_tea_leaves_handoff_unwraps_nested_envelope() -> None:
    model = TeaLeavesHandoff.from_payload(
        {
            "tea_leaves_handoff": {
                "importance_signals": [{"signal": "x" * 20}],
                "implicit_criteria": [{"criterion": "y" * 20}],
            }
        }
    )
    assert len(model.importance_signals) == 1
    assert len(model.implicit_criteria) == 1


def test_validate_real_eval_handoff_when_present() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "rag_storage/mcpp_rfp/skill_runs/readiness-frame-eval"
        / "20260613_012727_build_the_mission_readiness_fram/artifacts/eval_handoff.json"
    )
    if not path.is_file():
        pytest.skip("fixture handoff not on disk")
    model = validate_handoff_file(path)
    assert isinstance(model, EvalHandoff)
    assert len(model.eval_crosswalk) >= 1