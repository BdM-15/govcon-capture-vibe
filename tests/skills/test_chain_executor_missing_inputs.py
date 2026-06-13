"""Tests for chain step missing-input parsing."""

from __future__ import annotations

from src.skills.chain_executor import SkillChainExecutor


def test_extract_missing_inputs_ignores_success_bullet_lists() -> None:
    response = """**Mission Readiness Frame complete.** Artifact `artifacts/workload_handoff.json` emitted with:

- `workload_enablers[]` (7 contract mechanisms)
- `claim_gaps[]` (5 missing inputs the customer can supply for a fuller crosswalk)
- `pain_points_and_opportunities[]` (3 themes - one latent, two structural)
"""
    assert SkillChainExecutor._extract_missing_inputs(response) == []


def test_extract_missing_inputs_collects_exact_gaps_header() -> None:
    response = """**GAP IDENTIFIED - Cannot fully satisfy quality gate.**

**Exact gaps (per quality gate):**
- Missing incumbent PIID
- No workload spreadsheet
"""
    assert SkillChainExecutor._extract_missing_inputs(response) == [
        "Missing incumbent PIID",
        "No workload spreadsheet",
    ]


def test_extract_missing_inputs_collects_dedicated_section() -> None:
    response = """Handoff complete.

Missing inputs:
- Full Section M factor list with subfactor names
- QASP threshold tables for each deliverable
"""
    assert SkillChainExecutor._extract_missing_inputs(response) == [
        "Full Section M factor list with subfactor names",
        "QASP threshold tables for each deliverable",
    ]