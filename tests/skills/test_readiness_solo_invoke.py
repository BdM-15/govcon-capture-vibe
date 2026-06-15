"""Tests for solo readiness micro-skill invoke and assess."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.skills.chain_models import ChainStepRun
from src.skills.graphs.langgraph_chain_runner import use_langgraph_for_spec
from src.skills.handoff_quality import _SKILL_EXPECTED_HANDOFF
from src.skills.readiness_solo_invoke import (
    READINESS_SOLO_STEP_IDS,
    assess_readiness_solo_step,
    build_readiness_solo_chain_spec,
    build_solo_invoke_http_payload,
    resolve_solo_compile_input_artifacts,
)


def test_build_readiness_solo_chain_spec_compile_wires_solo_run_handoffs() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    refs = resolve_solo_compile_input_artifacts(
        repo_root=repo_root,
        workspace_name="mcpp_rfp",
    )
    assert len(refs) >= 6
    spec = build_readiness_solo_chain_spec("compile", "Build MRF.")
    step = spec.steps[0]
    assert step.id == "compile"
    assert len(step.input_artifacts) >= 6
    filenames = {artifact.filename for artifact in step.input_artifacts}
    assert "eval_handoff.json" in filenames
    assert "workload_handoff.json" in filenames


def test_build_readiness_solo_chain_spec_clears_upstream_dependencies() -> None:
    spec = build_readiness_solo_chain_spec("pains", "Build MRF.")
    step = spec.steps[0]
    assert step.id == "pains"
    assert step.depends_on == []
    assert step.input_artifacts == []
    assert step.artifact_requirements == []


def test_build_readiness_solo_chain_spec_workload_uses_pipeline_context() -> None:
    spec = build_readiness_solo_chain_spec(
        "workload",
        "Build the Mission Readiness Frame from the solicitation package.",
    )
    assert spec.name == "solo-workload"
    assert len(spec.steps) == 1
    step = spec.steps[0]
    assert step.id == "workload"
    assert step.skill == "readiness-frame-workload"
    assert step.context.get("langgraph_step_pipeline") is True
    assert spec.context.get("preset") == "readiness-solo"
    assert spec.context.get("solo_step_id") == "workload"


def test_readiness_solo_step_ids_match_micro_skills() -> None:
    assert "workload" in READINESS_SOLO_STEP_IDS
    assert "eval" in READINESS_SOLO_STEP_IDS
    assert "compile" in READINESS_SOLO_STEP_IDS


def test_use_langgraph_for_readiness_solo_preset() -> None:
    spec = build_readiness_solo_chain_spec("workload", "Build MRF.")
    assert use_langgraph_for_spec(spec) is True


def test_assess_readiness_solo_step_passes_valid_workload_handoff(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "readiness-frame-workload" / "run-1"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    handoff_name = _SKILL_EXPECTED_HANDOFF["readiness-frame-workload"]
    (artifacts / handoff_name).write_text(
        json.dumps(
            {
                "mission_readiness_frame": {
                    "readiness_outcome": (
                        "Program office expects integrated logistics readiness across "
                        "all maintenance centers with measurable sustainment outcomes."
                    ),
                },
                "workload_enablers": [
                    {
                        "enabler": "Integrated supply support",
                        "source_chunk_ids": ["chunk-abc123"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = assess_readiness_solo_step(
        step_id="workload",
        run_dir=run_dir,
        workspace_root=tmp_path,
        finish_reason="stop",
        warnings=[],
    )
    assert result.passed is True
    assert result.errors == []
    assert result.handoff_path.endswith(handoff_name)


def test_assess_readiness_solo_step_fails_empty_workload_handoff(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "readiness-frame-workload" / "run-2"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    handoff_name = _SKILL_EXPECTED_HANDOFF["readiness-frame-workload"]
    (artifacts / handoff_name).write_text(json.dumps({}), encoding="utf-8")

    result = assess_readiness_solo_step(
        step_id="workload",
        run_dir=run_dir,
        workspace_root=tmp_path,
        finish_reason="stop",
        warnings=[],
    )
    assert result.passed is False
    assert any("workload_handoff" in err for err in result.errors)


def test_build_solo_invoke_http_payload_uses_readiness_solo_preset() -> None:
    payload = build_solo_invoke_http_payload(
        "workload",
        "Build the Mission Readiness Frame from the solicitation package.",
    )
    assert payload["preset"] == "readiness-solo"
    assert payload["solo_step_id"] == "workload"
    assert "prompt" in payload


def test_build_readiness_solo_chain_spec_rejects_unknown_step() -> None:
    with pytest.raises(KeyError, match="unknown readiness step_id"):
        build_readiness_solo_chain_spec("not-a-step", "Build MRF.")