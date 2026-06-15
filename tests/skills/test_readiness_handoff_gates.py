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