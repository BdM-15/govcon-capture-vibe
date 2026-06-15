"""Tests for shared readiness handoff gate helpers."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.readiness_handoff_gates import validate_handoff_run
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