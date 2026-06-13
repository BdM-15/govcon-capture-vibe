"""Tests for platform depth-gate helpers."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.depth_gate import (
    depth_continue_message,
    make_depth_continue_fn,
    resolve_finish_reason,
)
from src.skills.skill_local_tools import SkillToolsHooks, load_skill_tool_module


def _mission_hooks():
    skill_dir = Path(__file__).resolve().parents[2] / ".github" / "skills" / "mission-readiness-framer"
    module = load_skill_tool_module(skill_dir, "mission_readiness_tools")
    return SkillToolsHooks(
        artifact_continue=module.artifact_continue_message,
        validate_run=module.validate_skill_run,
        write_depth_audit=module.write_depth_audit,
        validate_write_file=module.validate_write_file,
    )


def test_depth_continue_fires_on_thin_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "brief.md").write_text("# Brief\n\n## 5. Eval Cross-Walk\n\n| a | b |\n", encoding="utf-8")
    (artifacts / "mission_readiness_frame.json").write_text(
        json.dumps(
            {
                "customer_pain_points": [],
                "current_methods": [],
                "innovation_opportunities": [],
                "importance_signals": [],
                "implicit_criteria": [],
                "win_theme_candidates": [],
                "verbatim_extracts": [],
                "eval_crosswalk": [],
                "clarification_questions": [],
            }
        ),
        encoding="utf-8",
    )

    hooks = _mission_hooks()
    message = depth_continue_message(run_dir, hooks=hooks)
    assert message is not None
    assert "NOT complete" in message or "incomplete" in message.lower()


def test_make_depth_continue_fn_returns_callable_for_mission_readiness() -> None:
    hooks = _mission_hooks()
    cont = make_depth_continue_fn(hooks)
    assert cont is not None


def test_resolve_finish_reason_marks_depth_incomplete() -> None:
    assert (
        resolve_finish_reason(
            loop_finish_reason="stop",
            depth_issues=["eval_crosswalk is empty"],
            hard_cap_hit=False,
        )
        == "depth_incomplete"
    )
    assert (
        resolve_finish_reason(
            loop_finish_reason="stop",
            depth_issues=[],
            hard_cap_hit=False,
        )
        == "stop"
    )