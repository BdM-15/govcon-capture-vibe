"""Tests for readiness content quality gates."""

from __future__ import annotations

from src.skills.readiness_content_gates import (
    acronym_issues_for_readiness_output,
    citation_issues_for_crosswalk_row,
    claim_gaps_brief_issues,
    is_boilerplate_text,
    substance_issues_for_crosswalk_row,
    tail_compression_issues_for_brief,
    undefined_acronyms,
    validate_eval_handoff_write,
)


def test_is_boilerplate_text_detects_template_crosswalk_language() -> None:
    assert is_boilerplate_text(
        "Proposal must demonstrate compliant approach, staffing, and proof for Factor 1."
    )
    assert is_boilerplate_text("Section M / PWS task clusters — refine during capture review")
    assert not is_boilerplate_text(
        "Volume III must map PWS 2.1 maintenance milestones to a surge staffing plan."
    )


def test_substance_issues_for_crosswalk_row_flags_boilerplate_fields() -> None:
    issues = substance_issues_for_crosswalk_row(
        {
            "evaluation_factor": "Factor 1",
            "pws_clusters": ["Section M / PWS task clusters — refine during capture review"],
            "readiness_link": "Proposal must demonstrate compliant approach, staffing, and proof.",
            "proof_expected": "Proposal must demonstrate compliant approach, staffing, and proof.",
        },
        index=1,
    )
    assert len(issues) >= 2


def test_validate_eval_handoff_write_blocks_legacy_factor_shape() -> None:
    blocked = validate_eval_handoff_write(
        path="artifacts/eval_handoff.json",
        content=(
            '{"eval_crosswalk":[{"factor":"Factor 1 Management","subfactor":"Org Structure",'
            '"plain_reasoning":"Evaluates organizational integration.","source_chunk_ids":["chunk-1"]}]}'
        ),
    )
    assert blocked is not None
    assert "legacy factor/subfactor" in blocked


def test_validate_eval_handoff_write_blocks_boilerplate_json() -> None:
    blocked = validate_eval_handoff_write(
        path="artifacts/eval_handoff.json",
        content=(
            '{"eval_crosswalk":[{"evaluation_factor":"Factor 1",'
            '"pws_clusters":["Section M / PWS task clusters — refine during capture review"],'
            '"readiness_link":"Proposal must demonstrate compliant approach, staffing, and proof.",'
            '"proof_expected":"Proposal must demonstrate compliant approach, staffing, and proof.",'
            '"source_chunk_ids":["chunk-1"]}]}'
        ),
    )
    assert blocked is not None
    assert "blocked" in blocked


def test_citation_issues_for_crosswalk_row_rejects_invented_chunk_ids() -> None:
    issues = citation_issues_for_crosswalk_row(
        {
            "evaluation_factor": "Factor 2 — Technical Approach",
            "source_chunk_ids": ["capset production subfactor"],
        },
        index=3,
    )
    assert any("invalid source_chunk_ids" in issue for issue in issues)


def test_citation_issues_for_crosswalk_row_rejects_formulaic_factor_labels() -> None:
    issues = citation_issues_for_crosswalk_row(
        {
            "evaluation_factor": "section m-5 factor 5 cost/price",
            "source_chunk_ids": ["chunk-abc123"],
        },
        index=2,
    )
    assert any("invented shorthand" in issue for issue in issues)


def test_tail_compression_issues_for_brief_flags_thin_back_sections() -> None:
    brief = "\n".join(
        [
            "# Mission Readiness Brief",
            "## Mission Readiness Frame",
            "A" * 900,
            "## Customer pain (program office)",
            "B" * 900,
            "## Importance signals",
            "C" * 900,
            "## Win-theme candidates",
            "- WT-001: short",
            "## Clarifications to file",
            "- Q1: gap",
        ]
    )
    issues = tail_compression_issues_for_brief(brief)
    assert issues


def test_claim_gaps_brief_issues_when_json_gaps_missing_from_brief() -> None:
    payload = {
        "claim_gaps": [
            "Factor 4 subfactor b not retrieved from Section M amendment 3",
            "PWS 5.2 transition staffing detail absent from package",
            "QASP surge metric thresholds not in retrieval set",
        ]
    }
    brief = "## Mission Readiness Frame\nSome analysis without gap coverage."
    issues = claim_gaps_brief_issues(payload, brief)
    assert issues


def test_undefined_acronyms_ignores_defined_and_allowlisted_tokens() -> None:
    text = (
        "The Quality Assurance Surveillance Plan (QASP) governs PWS performance. "
        "The Contractor Readiness Assessment (CRA) is due at kickoff."
    )
    assert undefined_acronyms(text) == []


def test_undefined_acronyms_accepts_plural_and_hyphen_designators() -> None:
    text = (
        "Acceptable Quality Levels (AQLs) govern sampling. Later QASP AQL failures matter. "
        "T-AKE (Dry Cargo/Ammunition Ship) class support requires post-exercise tracking."
    )
    assert undefined_acronyms(text) == []


def test_acronym_gate_ignores_structural_name_labels() -> None:
    issues = acronym_issues_for_readiness_output(
        brief_text="## Mission Readiness Frame\nAnalysis without method labels.",
        payload={
            "current_methods": [
                {"name": "QMSS for KPI control charts and JCM data entry"},
            ]
        },
    )
    assert issues == []


def test_undefined_acronyms_accepts_pre_mats_and_cpff_loe_definitions() -> None:
    text = (
        "Defects surface during Pre-MATS trials. "
        "Cost-Plus-Fixed-Fee Level-of-Effort (CPFF LOE) cost growth threatens readiness."
    )
    assert undefined_acronyms(text) == []