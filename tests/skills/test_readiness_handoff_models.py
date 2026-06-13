"""Tests for readiness handoff Pydantic contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.skills.readiness_handoff_models import (
    EvalCrosswalkRow,
    EvalHandoff,
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