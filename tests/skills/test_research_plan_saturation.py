"""Tests for surface saturation in retrieval plan."""

from __future__ import annotations

from pathlib import Path

import json

from src.skills.evidence_gates import SATURATION_STRIKES_REQUIRED
from src.skills.research_harness import init_harness_state, load_harness_state, resolve_harness_config
from src.skills.research_plan import (
    auto_saturate_stalled_surfaces,
    close_retrieval_plan,
    retrieval_plan_complete,
    update_surface_after_kg_chunks,
)
from src.skills.skill_models import Skill, parse_frontmatter


def _mission_skill() -> Skill:
    skill_dir = Path(__file__).resolve().parents[2] / ".github" / "skills" / "mission-readiness-framer"
    skill_md = skill_dir / "SKILL.md"
    frontmatter, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    return Skill(
        name="mission-readiness-framer",
        path=str(skill_dir),
        skill_md_path=str(skill_md),
        frontmatter=frontmatter,
        body_md=body,
    )


def test_surface_saturates_after_one_zero_chunk_pass() -> None:
    assert SATURATION_STRIKES_REQUIRED == 1
    state = {
        "plan_surfaces": [
            {
                "id": "evaluation",
                "label": "Evaluation",
                "keywords": ["evaluation"],
                "status": "pending",
                "kg_chunks_attempts": 0,
            }
        ]
    }
    update_surface_after_kg_chunks(state, query="evaluation factors section m", new_chunk_count=0)
    assert state["plan_surfaces"][0]["status"] == "saturated"
    assert state["plan_surfaces"][0]["zero_chunk_strikes"] == 1


def test_auto_saturate_stalled_surfaces_marks_pending_zero_yield() -> None:
    state = {
        "kg_entities_satisfied": True,
        "plan_surfaces": [
            {"id": "tea_leaves", "status": "pending", "kg_chunks_attempts": 1, "last_new_chunks": 0},
            {"id": "background", "status": "retrieved", "kg_chunks_attempts": 1, "last_new_chunks": 3},
        ],
    }
    count = auto_saturate_stalled_surfaces(state)
    assert count == 1
    assert state["plan_surfaces"][0]["status"] == "saturated"
    assert retrieval_plan_complete(state) is True


def test_close_retrieval_plan_syncs_plan_file(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    config = resolve_harness_config(_mission_skill())
    init_harness_state(run_dir, config)
    state = load_harness_state(run_dir)
    assert state is not None
    state["kg_entities_satisfied"] = True
    for surface in state.get("plan_surfaces") or []:
        if isinstance(surface, dict):
            surface["status"] = "retrieved"
    state["plan_surfaces"][-1]["status"] = "pending"
    state["plan_surfaces"][-1]["kg_chunks_attempts"] = 1
    state["plan_surfaces"][-1]["last_new_chunks"] = 0
    from src.skills.research_harness import save_harness_state

    save_harness_state(run_dir, state)

    assert close_retrieval_plan(run_dir) is True
    plan = json.loads((run_dir / "artifacts" / "retrieval_plan.json").read_text(encoding="utf-8"))
    assert plan.get("plan_complete") is True