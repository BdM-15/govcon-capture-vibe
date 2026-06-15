"""Tests for readiness handoff quality gates."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.chain_step_gates import apply_step_quality_gate
from src.skills.evidence_gates import (
    DEFAULT_COVERAGE_MIN_RATIO,
    check_coverage_contract,
    minimum_required_crosswalk_rows,
)
from src.skills.handoff_quality import (
    step_quality_errors,
    validate_handoff_artifact,
    validate_step_handoffs,
)


def _write_eval_entities(workspace: Path, names: list[str]) -> None:
    records = []
    for name in names:
        records.append(
            {
                "entity_type": "evaluation_factor",
                "entity_name": name,
            }
        )
    (workspace / "vdb_entities.json").write_text(
        json.dumps({"data": records}),
        encoding="utf-8",
    )


def test_check_coverage_contract_requires_ratio_of_material_rows(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_eval_entities(workspace, [f"Factor {index}" for index in range(1, 11)])

    artifact = {
        "eval_crosswalk": [
            {
                "evaluation_factor": "Factor 1",
                "readiness_link": "x" * 60,
                "proof_expected": "y" * 30,
                "source_chunk_ids": ["chunk-abc"],
                "pws_clusters": ["PWS 1"],
            }
        ]
    }
    issues = check_coverage_contract(
        workspace_dir=workspace,
        coverage_contract={
            "required_entity_types": ["evaluation_factor", "subfactor"],
            "rule": "one_row_per_entity",
            "rows_key": "eval_crosswalk",
            "min_coverage_ratio": DEFAULT_COVERAGE_MIN_RATIO,
        },
        artifact=artifact,
    )
    assert issues
    assert issues[0].startswith("coverage:")


def test_check_coverage_contract_accepts_named_claim_gaps(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    names = [f"Factor {index}" for index in range(1, 6)]
    _write_eval_entities(workspace, names)

    artifact = {
        "eval_crosswalk": [
            {
                "evaluation_factor": "Factor 1",
                "readiness_link": "x" * 60,
                "proof_expected": "y" * 30,
                "source_chunk_ids": ["chunk-abc"],
                "pws_clusters": ["PWS 1"],
            },
            {
                "evaluation_factor": "Factor 2",
                "readiness_link": "x" * 60,
                "proof_expected": "y" * 30,
                "source_chunk_ids": ["chunk-def"],
                "pws_clusters": ["PWS 2"],
            },
        ],
        "claim_gaps": [
            "eval_crosswalk: missing row for Factor 3",
            "eval_crosswalk: missing row for Factor 4",
            "eval_crosswalk: missing row for Factor 5",
        ],
    }
    issues = check_coverage_contract(
        workspace_dir=workspace,
        coverage_contract={
            "required_entity_types": ["evaluation_factor", "subfactor"],
            "rule": "one_row_per_entity",
            "rows_key": "eval_crosswalk",
            "min_coverage_ratio": 0.8,
        },
        artifact=artifact,
    )
    assert not issues


def test_validate_handoff_artifact_flags_thin_eval_handoff(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_eval_entities(workspace, [f"Factor {index}" for index in range(1, 11)])
    handoff_path = tmp_path / "eval_handoff.json"
    handoff_path.write_text(
        json.dumps(
            {
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Factor 1",
                        "readiness_link": "x" * 60,
                        "proof_expected": "y" * 30,
                        "source_chunk_ids": ["chunk-abc"],
                        "pws_clusters": ["PWS 1"],
                    }
                ],
                "claim_gaps": [],
            }
        ),
        encoding="utf-8",
    )
    issues = validate_handoff_artifact(
        "eval_handoff.json",
        handoff_path,
        workspace_dir=workspace,
    )
    assert any(issue.startswith("coverage:") for issue in issues)


def test_apply_step_quality_gate_fails_chain_step(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_eval_entities(workspace, [f"Factor {index}" for index in range(1, 6)])
    (workspace / "vdb_chunks.json").write_text("{}", encoding="utf-8")

    eval_run_dir = workspace / "runs" / "eval-run"
    artifacts = eval_run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "eval_handoff.json").write_text(
        json.dumps(
            {
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Factor 1",
                        "readiness_link": "x" * 60,
                        "proof_expected": "y" * 30,
                        "source_chunk_ids": ["chunk-abc"],
                        "pws_clusters": ["PWS 1"],
                    }
                ],
                "claim_gaps": [],
            }
        ),
        encoding="utf-8",
    )

    class _StepRun:
        run_dir = str(eval_run_dir)
        skill = "readiness-frame-eval"
        artifacts = [{"name": "eval_handoff.json"}]
        status = "completed"
        error = ""
        warnings: list[str] = []

    step_run = _StepRun()
    failed = apply_step_quality_gate(
        step_run,
        finish_reason="complete",
        warnings=[],
        workspace_root=workspace,
    )
    assert failed is True
    assert step_run.status == "failed"
    assert "handoff_quality" in step_run.error or "coverage:" in step_run.error


def test_minimum_required_crosswalk_rows_uses_workspace_inventory(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_eval_entities(
        workspace,
        [f"Factor {index} Management" for index in range(1, 11)],
    )
    assert minimum_required_crosswalk_rows(workspace) == 8


def test_step_quality_errors_blocks_compiler_on_substance_not_line_count(
    tmp_path: Path,
) -> None:
    compiler_run_dir = tmp_path / "compiler_run"
    artifacts = compiler_run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "chain_context.json").write_text(
        json.dumps({"role": "compiler"}),
        encoding="utf-8",
    )
    long_brief = "# Mission Readiness Frame Brief\n\n" + ("Generic readiness narrative. " * 2000)
    (artifacts / "brief.md").write_text(long_brief, encoding="utf-8")
    shared_link = (
        "Program office evaluates organizational integration because weak performance "
        "degrades mission readiness and eval confidence across the contract period."
    )
    (artifacts / "mission_readiness_frame.json").write_text(
        json.dumps(
            {
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Factor 1 Management",
                        "readiness_link": shared_link,
                        "proof_expected": "y" * 30,
                        "source_chunk_ids": ["chunk-abc"],
                    },
                    {
                        "evaluation_factor": "Factor 2 Technical",
                        "readiness_link": shared_link,
                        "proof_expected": "y" * 30,
                        "source_chunk_ids": ["chunk-abc"],
                    },
                    {
                        "evaluation_factor": "Factor 3 Past Performance",
                        "readiness_link": shared_link.replace("organizational", "operational"),
                        "proof_expected": "y" * 30,
                        "source_chunk_ids": ["chunk-abc"],
                    },
                ],
                "verbatim_extracts": [],
                "claim_gaps": [],
            }
        ),
        encoding="utf-8",
    )

    class _StepRun:
        run_dir = str(compiler_run_dir)
        skill = "mission-readiness-framer"
        artifacts = []

    errors = step_quality_errors(
        finish_reason="complete",
        warnings=[],
        step_run=_StepRun(),
        workspace_root=tmp_path,
    )
    assert errors
    assert not any("only" in error and "lines" in error for error in errors)


def test_step_quality_errors_ignores_depth_incomplete_when_handoff_passes(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_eval_entities(workspace, [f"Factor {index}" for index in range(1, 6)])
    (workspace / "vdb_chunks.json").write_text("{}", encoding="utf-8")
    slice_run_dir = workspace / "run"
    artifacts = slice_run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "eval_handoff.json").write_text(
        json.dumps(
            {
                "eval_crosswalk": [
                    {
                        "evaluation_factor": f"Factor {index} Management Approach",
                        "readiness_link": "x" * 60,
                        "proof_expected": "y" * 30,
                        "source_chunk_ids": ["chunk-abc"],
                        "pws_clusters": ["PWS 1"],
                    }
                    for index in range(1, 5)
                ],
                "claim_gaps": ["eval_crosswalk: missing row for Factor 5 Management Approach"],
            }
        ),
        encoding="utf-8",
    )

    class _StepRun:
        run_dir = str(slice_run_dir)
        skill = "readiness-frame-eval"
        artifacts = [{"name": "eval_handoff.json"}]

    errors = step_quality_errors(
        finish_reason="depth_incomplete",
        warnings=["depth_audit: eval_crosswalk row 2 has invalid source_chunk_ids (fake)"],
        step_run=_StepRun(),
        workspace_root=workspace,
    )
    assert not any("finish_reason=depth_incomplete" in error for error in errors)


def test_validate_step_handoffs_returns_errors_not_warnings(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_eval_entities(workspace, ["Factor 1", "Factor 2", "Factor 3", "Factor 4", "Factor 5"])
    (workspace / "vdb_chunks.json").write_text("{}", encoding="utf-8")
    slice_run_dir = workspace / "run"
    artifacts = slice_run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "eval_handoff.json").write_text(
        json.dumps({"eval_crosswalk": [], "claim_gaps": []}),
        encoding="utf-8",
    )

    class _StepRun:
        run_dir = str(slice_run_dir)
        skill = "readiness-frame-eval"
        artifacts = [{"name": "eval_handoff.json"}]

    errors = validate_step_handoffs(_StepRun(), workspace)
    assert errors
    assert errors[0].startswith("handoff_quality:")


def test_validate_step_handoffs_eval_does_not_block_on_undefined_acronyms(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_eval_entities(workspace, [f"Factor {index}" for index in range(1, 6)])
    (workspace / "vdb_chunks.json").write_text("{}", encoding="utf-8")
    slice_run_dir = workspace / "eval-run"
    artifacts = slice_run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "eval_handoff.json").write_text(
        json.dumps(
            {
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Factor 1 Past Performance",
                        "readiness_link": (
                            "Program cites TECV and SB set-aside rules for this acquisition "
                            "with detailed sustainment proof expectations."
                        ),
                        "proof_expected": "y" * 30,
                        "source_chunk_ids": ["chunk-abc"],
                        "pws_clusters": ["PWS 1"],
                    }
                ],
                "claim_gaps": [],
            }
        ),
        encoding="utf-8",
    )

    class _StepRun:
        run_dir = str(slice_run_dir)
        skill = "readiness-frame-eval"

    errors = validate_step_handoffs(_StepRun(), workspace)
    assert not any("undefined acronyms" in error.lower() for error in errors)