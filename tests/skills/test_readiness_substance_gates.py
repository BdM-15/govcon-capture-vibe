"""Tests for substance-based readiness quality gates."""

from __future__ import annotations

from src.skills.readiness_content_gates import crosswalk_repetition_issues


def test_crosswalk_repetition_issues_flags_recycled_readiness_links() -> None:
    shared = (
        "Program office evaluates organizational integration and staffing depth because "
        "weak performance degrades mission readiness and eval confidence across the contract."
    )
    crosswalk = [
        {
            "evaluation_factor": "Factor 1 Management",
            "readiness_link": shared,
            "proof_expected": "y" * 30,
        },
        {
            "evaluation_factor": "Factor 2 Technical",
            "readiness_link": shared,
            "proof_expected": "z" * 30,
        },
        {
            "evaluation_factor": "Factor 3 Past Performance",
            "readiness_link": shared.replace("organizational", "operational"),
            "proof_expected": "w" * 30,
        },
    ]
    issues = crosswalk_repetition_issues(crosswalk)
    assert issues
    assert "near-duplicate" in issues[0]


def test_crosswalk_repetition_issues_accepts_distinct_rows() -> None:
    crosswalk = [
        {
            "evaluation_factor": "Factor 1 Management",
            "readiness_link": "Management approach must show succession planning for MCSF-BI depot rotations and CDRL A001 staffing traceability with cited PWS 3.2 language.",
            "proof_expected": "y" * 30,
        },
        {
            "evaluation_factor": "Factor 4 Past Performance",
            "readiness_link": "Past performance relevancy ratings determine confidence that contractor can sustain ME operational status reporting without lag during OPTEMPO surges.",
            "proof_expected": "z" * 30,
        },
    ]
    assert not crosswalk_repetition_issues(crosswalk)