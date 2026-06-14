"""Tests for platform eval finalize helpers."""

from __future__ import annotations

from src.skills.platform_eval_finalize import split_eval_gate_issues


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