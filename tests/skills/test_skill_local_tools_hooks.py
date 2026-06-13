"""Tests for generic skill *_tools.py platform hooks."""

from __future__ import annotations

from pathlib import Path

from src.skills.skill_local_tools import resolve_skill_tools_hooks


def test_resolve_skill_tools_hooks_finds_mission_readiness_hooks() -> None:
    skill_dir = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "skills"
        / "mission-readiness-framer"
    )
    hooks = resolve_skill_tools_hooks(skill_dir)
    assert hooks.artifact_continue is not None
    assert hooks.validate_write_file is not None
    assert hooks.validate_run is not None
    assert hooks.write_depth_audit is not None