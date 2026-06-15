"""Tests for readiness content quality gates."""

from __future__ import annotations

from src.skills.readiness_content_gates import (
    acronym_issues_for_eval_handoff,
    acronym_issues_for_readiness_output,
    acronym_warnings_for_text,
    apply_acronym_expansions,
    apply_known_acronym_expansions_to_eval_payload,
    apply_known_acronym_expansions_to_frame_payload,
    build_acronym_expansion_map,
    citation_issues_for_crosswalk_row,
    claim_gaps_brief_issues,
    is_boilerplate_text,
    substance_issues_for_crosswalk_row,
    tail_compression_issues_for_brief,
    undefined_acronyms,
    validate_eval_handoff_write,
    verbatim_extract_issues,
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


def test_apply_known_acronym_expansions_to_eval_payload() -> None:
    payload = {
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
    expanded = apply_known_acronym_expansions_to_eval_payload(payload)
    assert "Contractor Performance Assessment Reporting System (CPARS)" in str(
        expanded["eval_crosswalk"][0]["readiness_link"]
    )
    assert not acronym_issues_for_eval_handoff(expanded)


def test_citation_issues_for_crosswalk_row_accepts_inventory_formulaic_labels() -> None:
    issues = citation_issues_for_crosswalk_row(
        {
            "evaluation_factor": "Factor 5 Cost/Price (evaluation_factor)",
            "source_chunk_ids": ["chunk-abc123"],
        },
        index=2,
        known_factor_labels={"factor 5 cost/price", "m-5 cost realism evaluation"},
    )
    assert not any("invented shorthand" in issue for issue in issues)


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


def test_apply_known_acronym_expansions_to_frame_payload() -> None:
    payload = {
        "readiness_outcome": "MCPP sustainment uses RCP and ISO controls at MCSF-BI.",
        "eval_crosswalk": [],
        "verbatim_extracts": [],
    }
    expanded = apply_known_acronym_expansions_to_frame_payload(payload)
    text = expanded["readiness_outcome"]
    assert "Marine Corps Prepositioning Program (MCPP)" in text
    assert "Risk and Performance (RCP)" in text
    assert not acronym_issues_for_readiness_output(brief_text="", payload=expanded)


def test_verbatim_extract_issues_passes_when_seeded() -> None:
    payload = {
        "verbatim_extracts": [{"quote": "Government language from Section M evaluation criteria."}],
        "eval_crosswalk": [{"source_chunk_ids": ["chunk-1"]}] * 3,
    }
    assert not verbatim_extract_issues(
        payload,
        crosswalk_has_citations=True,
        cited_crosswalk_rows=3,
    )


def test_acronym_issues_never_block_even_when_undefined() -> None:
    text = "Program cites TECV and SB set-aside rules for this acquisition."
    assert acronym_issues_for_readiness_output(brief_text=text, payload=None) == []
    assert acronym_warnings_for_text(text, label="eval") != []


def test_build_acronym_expansion_map_prefers_scratchpad_evidence() -> None:
    evidence = (
        "Commanding Officer (CMDO) P5000.11 governs maintenance. "
        "Data Item (DI) schedules drive inspection cycles."
    )
    text = "Compliance with CMDO P5000.11 and ISO/DI discipline is required."
    expansion_map = build_acronym_expansion_map(evidence)
    expanded = apply_acronym_expansions(text, expansion_map)
    assert "Commanding Officer (CMDO)" in expanded
    assert "Data Item (DI)" in expanded


def test_undefined_acronyms_accepts_pre_mats_and_cpff_loe_definitions() -> None:
    text = (
        "Defects surface during Pre-MATS trials. "
        "Cost-Plus-Fixed-Fee Level-of-Effort (CPFF LOE) cost growth threatens readiness."
    )
    assert undefined_acronyms(text) == []