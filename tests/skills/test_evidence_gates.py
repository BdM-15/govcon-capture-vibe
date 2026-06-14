"""Tests for deterministic evidence gates."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.evidence_gates import (
    SATURATION_STRIKES_REQUIRED,
    check_coverage_contract,
    is_placeholder_text,
    run_deterministic_audit,
)


def test_saturation_strikes_required_is_two() -> None:
    assert SATURATION_STRIKES_REQUIRED == 2


def test_is_placeholder_text() -> None:
    assert is_placeholder_text("TBD")
    assert is_placeholder_text("")
    assert not is_placeholder_text("Fleet readiness shortfall")


def test_check_coverage_contract_flags_missing_eval_rows(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "vdb_entities.json").write_text(
        json.dumps(
            {
                "data": [
                    {"entity_type": "evaluation_factor", "entity_name": "Technical"},
                    {"entity_type": "evaluation_factor", "entity_name": "Management"},
                    {"entity_type": "subfactor", "entity_name": "Approach"},
                ]
            }
        ),
        encoding="utf-8",
    )
    artifact = {"eval_crosswalk": [{"evaluation_factor": "Technical"}]}
    issues = check_coverage_contract(
        workspace_dir=workspace,
        coverage_contract={
            "required_entity_types": ["evaluation_factor", "subfactor"],
            "rule": "one_row_per_entity",
            "rows_key": "eval_crosswalk",
        },
        artifact=artifact,
    )
    assert issues
    assert "coverage" in issues[0]


def test_run_deterministic_audit_flags_invalid_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "handoff.json").write_text("{not json", encoding="utf-8")
    result = run_deterministic_audit(
        run_dir=run_dir,
        workspace_dir=tmp_path,
        artifact_paths=[artifacts / "handoff.json"],
    )
    assert not result["pass"]
    assert any("invalid JSON" in issue for issue in result["issues"])