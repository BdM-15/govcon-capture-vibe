"""Tests for shared readiness handoff gate helpers."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.readiness_handoff_gates import validate_handoff_run
from src.skills.readiness_handoff_models import normalize_pains_row
from src.skills.skill_local_tools import resolve_skill_run_validator


_MICRO_SKILLS = (
    ("readiness-frame-workload", "workload_handoff.json"),
    ("readiness-frame-pains", "pains_handoff.json"),
    ("readiness-frame-modernization", "modernization_handoff.json"),
    ("readiness-frame-tea-leaves", "tea_leaves_handoff.json"),
    ("readiness-frame-win-themes", "win_themes_handoff.json"),
    ("readiness-frame-eval", "eval_handoff.json"),
    ("readiness-frame-external-research", "capability_overlay_handoff.json"),
)


def test_all_micro_skills_declare_validate_skill_run() -> None:
    repo = Path(__file__).resolve().parents[2]
    for skill_name, _deliverable in _MICRO_SKILLS:
        skill_dir = repo / ".github" / "skills" / skill_name
        assert skill_dir.is_dir(), skill_name
        assert resolve_skill_run_validator(skill_dir) is not None, skill_name


def test_normalize_tea_leaves_row_extracts_embedded_chunk_ids() -> None:
    from src.skills.readiness_handoff_models import normalize_tea_leaves_signal_row

    row = normalize_tea_leaves_signal_row(
        {
            "signal": "Best Value Tradeoff emphasis",
            "repetition": (
                "Section M references (chunk-5299cdff54e8ebf39576010b6e6a2f61, "
                "doc-18757251a21fe8fa5ce652e4731b298b-mm-table-000)"
            ),
            "hot_button": "Outstanding requires demonstrated innovation",
            "eval_echo": "Non-cost factors outweigh price",
        }
    )
    assert row["source_chunk_ids"]
    assert "chunk-5299cdff54e8ebf39576010b6e6a2f61" in row["source_chunk_ids"]
    assert str(row.get("rationale") or "").strip()


def test_tea_leaves_gate_requires_cited_object_rows(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-tea-leaves"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "tea_leaves_handoff.json").write_text(
        json.dumps(
            {
                "importance_signals": [
                    "Plain string signal [chunk-abc123]",
                    {
                        "signal": "Short",
                        "source_chunk_ids": ["chunk-abc124"],
                    },
                ],
                "implicit_criteria": [
                    {
                        "criterion": "Thin only",
                        "source_role": "program_office",
                        "source_chunk_ids": ["chunk-abc125"],
                    }
                ],
                "claim_gaps": [],
            }
        ),
        encoding="utf-8",
    )
    issues = validate_handoff_run(run_dir, deliverable="tea_leaves_handoff.json")
    assert any("importance_signals must be objects" in issue for issue in issues)
    assert any("importance_signals needs >= 3" in issue for issue in issues)
    assert any("implicit_criteria needs >= 2" in issue for issue in issues)


def test_tea_leaves_hook_matches_shared_gate(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-tea-leaves-hook"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "tea_leaves_handoff.json").write_text(json.dumps({}), encoding="utf-8")

    repo = Path(__file__).resolve().parents[2]
    skill_dir = repo / ".github" / "skills" / "readiness-frame-tea-leaves"
    validate_run = resolve_skill_run_validator(skill_dir)
    assert validate_run is not None

    hook_issues = validate_run(run_dir)
    shared_issues = validate_handoff_run(run_dir, deliverable="tea_leaves_handoff.json")
    assert hook_issues == shared_issues
    assert hook_issues


def test_modernization_gate_requires_object_rows_with_substance(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-modernization"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "modernization_handoff.json").write_text(
        json.dumps(
            {
                "current_methods": [
                    "Plain string method [chunk-abc123]",
                    {
                        "method": "Short",
                        "implied_by": "Too thin.",
                        "source_chunk_ids": ["chunk-abc124"],
                    },
                ],
                "innovation_opportunities": [
                    {
                        "opportunity": "Thin only",
                        "value": "Too short.",
                        "source_chunk_ids": ["chunk-abc127"],
                    }
                ],
                "claim_gaps": [],
            }
        ),
        encoding="utf-8",
    )
    issues = validate_handoff_run(run_dir, deliverable="modernization_handoff.json")
    assert any("current_methods must be objects" in issue for issue in issues)
    assert any("current_methods needs >= 3" in issue for issue in issues)
    assert any("innovation_opportunities needs >= 2" in issue for issue in issues)


def test_modernization_gate_flags_thin_substance_rows(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-modernization-thin"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    good_method = {
        "method": "QMSS performance tracking",
        "implied_by": (
            "QASP E-1 inspection and CDRL 2036 maintenance management deliverables "
            "require real-time performance visibility."
        ),
        "tooling": "QMSS software",
        "fit_to_scope": "high",
        "source_chunk_ids": ["chunk-abc125"],
    }
    good_innovation = {
        "opportunity": "Predictive maintenance analytics",
        "value": (
            "Quality up through higher equipment availability; cost down through "
            "fewer emergency repairs."
        ),
        "customer_grounded": True,
        "fit_to_scope": "high",
        "source_chunk_ids": ["chunk-abc126"],
    }
    (artifacts / "modernization_handoff.json").write_text(
        json.dumps(
            {
                "current_methods": [
                    good_method,
                    good_method,
                    {
                        "method": "Short",
                        "implied_by": "Too thin.",
                        "source_chunk_ids": ["chunk-abc124"],
                    },
                ],
                "innovation_opportunities": [
                    good_innovation,
                    {
                        "opportunity": "Thin",
                        "value": "Too short.",
                        "source_chunk_ids": ["chunk-abc127"],
                    },
                ],
                "claim_gaps": [],
            }
        ),
        encoding="utf-8",
    )
    issues = validate_handoff_run(run_dir, deliverable="modernization_handoff.json")
    assert any("current_methods rows" in issue and "too thin" in issue for issue in issues)
    assert any(
        "innovation_opportunities rows" in issue and "too thin" in issue for issue in issues
    )


def test_modernization_hook_matches_shared_gate(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-modernization-hook"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "modernization_handoff.json").write_text(json.dumps({}), encoding="utf-8")

    repo = Path(__file__).resolve().parents[2]
    skill_dir = repo / ".github" / "skills" / "readiness-frame-modernization"
    validate_run = resolve_skill_run_validator(skill_dir)
    assert validate_run is not None

    hook_issues = validate_run(run_dir)
    shared_issues = validate_handoff_run(run_dir, deliverable="modernization_handoff.json")
    assert hook_issues == shared_issues
    assert hook_issues


def test_workload_gate_requires_object_rows_with_citations(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-prod"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "workload_handoff.json").write_text(
        json.dumps(
            {
                "readiness_outcome": (
                    "Program office owns Marine Corps prepositioned equipment readiness at "
                    "MCSF-BI DFSP sites — contract workload instruments FMC and PO attainment."
                ),
                "workload_enablers": [
                    "Plain string enabler one [chunk-abc123]",
                    "Plain string enabler two [chunk-abc124]",
                    "Plain string enabler three [chunk-abc125]",
                ],
                "failure_modes_feared": [
                    {
                        "failure_mode": "Missed PMCS",
                        "customer_impact": "FMC drops below threshold",
                        "source_chunk_ids": ["chunk-def456"],
                    },
                    {
                        "failure_mode": "Late CDRL",
                        "customer_impact": "Program office loses visibility",
                        "source_chunk_ids": ["chunk-def457"],
                    },
                    {
                        "failure_mode": "Transition gap",
                        "customer_impact": "Coverage void at POP start",
                        "source_chunk_ids": ["chunk-def458"],
                    },
                ],
                "claim_gaps": [],
            }
        ),
        encoding="utf-8",
    )
    issues = validate_handoff_run(run_dir, deliverable="workload_handoff.json")
    assert any("workload_enablers must be objects" in issue for issue in issues)


def test_normalize_pains_row_repairs_visibility_swap() -> None:
    row = normalize_pains_row(
        {
            "challenge_type": "latent",
            "rationale": (
                "CPFF LOE contract structure creates incentive misalignment where "
                "contractors may prioritize billing over readiness outcomes."
            ),
            "readiness_link": "Erodes cost discipline and true readiness gains for the program office.",
            "source_chunk_ids": ["chunk-abc123"],
        }
    )
    assert row["visibility"] == "latent"
    assert row["challenge_type"].startswith("CPFF LOE")
    assert len(row["challenge_type"]) >= 12


def test_pains_gate_requires_object_rows_with_substance(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-pains"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "pains_handoff.json").write_text(
        json.dumps(
            {
                "customer_pain_points": [
                    "Plain string pain one [chunk-abc123]",
                    {
                        "visibility": "explicit",
                        "challenge_type": "Short",
                        "rationale": "Too thin.",
                        "readiness_link": "Thin link.",
                        "source_chunk_ids": ["chunk-abc124"],
                    },
                    {
                        "visibility": "explicit",
                        "challenge_type": "Deferred maintenance spikes",
                        "rationale": (
                            "PWS and audit findings cite repeated corrective maintenance spikes "
                            "that erode equipment availability; program office bears readiness "
                            "degradation when prepositioned stocks fail during crisis activation."
                        ),
                        "readiness_link": (
                            "Directly threatens prepositioned equipment readiness outcome the "
                            "customer owns for crisis response activation."
                        ),
                        "source_chunk_ids": ["chunk-abc125"],
                    },
                ],
                "claim_gaps": [],
            }
        ),
        encoding="utf-8",
    )
    issues = validate_handoff_run(run_dir, deliverable="pains_handoff.json")
    assert any("must be objects" in issue for issue in issues)
    assert any("too thin" in issue for issue in issues)


def test_pains_hook_matches_shared_gate(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-pains-hook"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "pains_handoff.json").write_text(json.dumps({}), encoding="utf-8")

    repo = Path(__file__).resolve().parents[2]
    skill_dir = repo / ".github" / "skills" / "readiness-frame-pains"
    validate_run = resolve_skill_run_validator(skill_dir)
    assert validate_run is not None

    hook_issues = validate_run(run_dir)
    shared_issues = validate_handoff_run(run_dir, deliverable="pains_handoff.json")
    assert hook_issues == shared_issues
    assert hook_issues


def test_workload_hook_matches_shared_gate(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "workload_handoff.json").write_text(json.dumps({}), encoding="utf-8")

    repo = Path(__file__).resolve().parents[2]
    skill_dir = repo / ".github" / "skills" / "readiness-frame-workload"
    validate_run = resolve_skill_run_validator(skill_dir)
    assert validate_run is not None

    hook_issues = validate_run(run_dir)
    shared_issues = validate_handoff_run(run_dir, deliverable="workload_handoff.json")
    assert hook_issues == shared_issues
    assert hook_issues