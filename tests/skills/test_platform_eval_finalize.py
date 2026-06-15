"""Tests for platform eval finalize helpers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.skills.eval_handoff_repair import repair_eval_handoff
from src.skills.platform_eval_finalize import finalize_eval_handoff, split_eval_gate_issues
from src.skills.readiness_content_gates import acronym_issues_for_eval_handoff


def test_split_eval_gate_issues_retriable_coverage() -> None:
    issues = [
        "coverage: eval_crosswalk rows 8/24 required",
        "undefined acronyms: CPARS, PPQ",
        "eval_handoff.json missing required field: claim_gaps",
    ]
    blocking, retriable = split_eval_gate_issues(issues)
    assert len(blocking) == 1
    assert "claim_gaps" in blocking[0]
    assert len(retriable) == 2
    assert any("coverage" in item for item in retriable)


def test_split_eval_gate_issues_empty_crosswalk_retriable() -> None:
    blocking, retriable = split_eval_gate_issues(
        ["eval_crosswalk is empty — add substantive rows or document gaps in claim_gaps[]"]
    )
    assert blocking == []
    assert len(retriable) == 1


def test_eval_needs_platform_expansion_empty_crosswalk(tmp_path: Path) -> None:
    from src.skills.platform_eval_finalize import (
        _eval_needs_platform_expansion,
        _scratchpad_has_grounded_evidence,
    )

    workspace = tmp_path / "ws"
    workspace.mkdir()
    run_dir = workspace / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "eval_handoff.json").write_text(
        json.dumps({"eval_crosswalk": [], "claim_gaps": ["Factor 1 — no evidence"]}),
        encoding="utf-8",
    )
    (artifacts / "research_scratchpad.md").write_text(
        "Evidence chunk-abc-123 from Section M.\n" * 40,
        encoding="utf-8",
    )
    assert _eval_needs_platform_expansion(run_dir, workspace) is True
    assert _scratchpad_has_grounded_evidence(run_dir) is True


def test_repair_eval_handoff_expands_known_acronyms(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "eval_handoff.json").write_text(
        json.dumps(
            {
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Factor 4 Past Performance",
                        "readiness_link": "Uses CPARS and CPFF with CBA mapping for labor rates.",
                        "proof_expected": "Submit CPARS references.",
                        "source_chunk_ids": ["chunk-1"],
                    }
                ],
                "claim_gaps": [],
            }
        ),
        encoding="utf-8",
    )

    assert repair_eval_handoff(run_dir) is True
    payload = json.loads((artifacts / "eval_handoff.json").read_text(encoding="utf-8"))
    assert not acronym_issues_for_eval_handoff(payload)


def test_finalize_eval_repairs_without_llm_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVAL_EXPANDER_LLM", raising=False)
    monkeypatch.delenv("EVAL_ADMIN_LLM", raising=False)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "vdb_chunks.json").write_text("{}", encoding="utf-8")
    run_dir = workspace / "skill_runs" / "readiness-frame-eval" / "run-1"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "eval_handoff.json").write_text(
        json.dumps(
            {
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Factor 4 Past Performance",
                        "readiness_link": "Uses CPARS and CPFF with CBA mapping for labor rates.",
                        "proof_expected": "Submit CPARS references.",
                        "source_chunk_ids": ["chunk-1"],
                    }
                ],
                "claim_gaps": [],
            }
        ),
        encoding="utf-8",
    )

    result = asyncio.run(
        finalize_eval_handoff(run_dir=run_dir, workspace_dir=workspace),
    )
    assert any("repaired_known_acronyms" in warning for warning in result["warnings"])
    payload = json.loads((artifacts / "eval_handoff.json").read_text(encoding="utf-8"))
    assert not acronym_issues_for_eval_handoff(payload)