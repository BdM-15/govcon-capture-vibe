"""Tests for methodical research retrieval plan guards."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.research_harness import (
    ResearchHarnessConfig,
    get_phase,
    init_harness_state,
    load_harness_state,
    record_tool_retrieval,
)
from src.skills.research_plan import (
    check_kg_chunks_plan,
    is_duplicate_query,
    retrieval_plan_complete,
)
from src.skills.tool_kg import tool_kg_chunks
from src.skills.tool_types import ToolContext


def _init_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    config = ResearchHarnessConfig()
    init_harness_state(run_dir, config)
    return run_dir


def test_is_duplicate_query_detects_near_duplicates() -> None:
    prior = ["QASP performance standards inspection acceptance criteria"]
    assert is_duplicate_query(
        "QASP performance standards inspection and acceptance criteria",
        prior,
    )
    assert not is_duplicate_query("transition plan phase-in Section H knowledge transfer", prior)


def test_retrieval_plan_complete_requires_entities_and_all_surfaces(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path)
    state = load_harness_state(run_dir)
    assert state is not None
    assert not retrieval_plan_complete(state)

    state["kg_entities_satisfied"] = True
    for surface in state.get("plan_surfaces") or []:
        if isinstance(surface, dict):
            surface["status"] = "retrieved"
    assert retrieval_plan_complete(state)


def test_check_kg_chunks_blocks_duplicate_without_vdb(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path)
    state = load_harness_state(run_dir)
    assert state is not None
    state["prior_queries"] = ["QASP performance standards inspection acceptance"]
    from src.skills.research_harness import save_harness_state

    save_harness_state(run_dir, state)

    blocked = check_kg_chunks_plan(
        run_dir,
        query="QASP performance standards inspection acceptance criteria",
        phase="retrieve",
    )
    assert blocked is not None
    assert blocked.payload.get("reason") == "duplicate_query"


def test_tool_kg_chunks_short_circuits_when_plan_complete(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path)
    state = load_harness_state(run_dir)
    assert state is not None
    state["kg_entities_satisfied"] = True
    for surface in state.get("plan_surfaces") or []:
        if isinstance(surface, dict):
            surface["status"] = "saturated"
    from src.skills.research_harness import save_harness_state

    save_harness_state(run_dir, state)

    async def _should_not_run(*_args, **_kwargs):
        raise AssertionError("retrieve_fn should not be called when plan is complete")

    ctx = ToolContext(
        skill_name="mission-readiness-framer",
        skill_dir=tmp_path,
        run_dir=run_dir,
        workspace_dir=tmp_path,
        workspace_name="demo",
        retrieve_fn=_should_not_run,
        research_harness_config=ResearchHarnessConfig(),
    )
    import asyncio

    result = asyncio.run(tool_kg_chunks(ctx, query="evaluation factors section m", top_k=20))
    assert result.payload.get("skipped") is True
    assert result.payload.get("reason") == "retrieval_plan_complete"


def test_record_tool_retrieval_advances_phase_when_plan_complete(tmp_path: Path) -> None:
    run_dir = _init_run(tmp_path)
    config = ResearchHarnessConfig()
    state = load_harness_state(run_dir)
    assert state is not None
    state["kg_entities_satisfied"] = True
    surfaces = state.get("plan_surfaces") or []
    for index, surface in enumerate(surfaces):
        if not isinstance(surface, dict):
            continue
        if index < len(surfaces) - 1:
            surface["status"] = "retrieved"
    from src.skills.research_harness import save_harness_state

    save_harness_state(run_dir, state)

    record_tool_retrieval(
        run_dir,
        tool_name="kg_chunks",
        arguments_json=json.dumps({"query": "transition plan phase-in amendments"}),
        payload_str=json.dumps(
            {
                "source_chunks": [
                    {"chunk_id": "chunk-final", "content": "Phase-in shall begin within 90 days."}
                ]
            }
        ),
        config=config,
    )
    assert get_phase(run_dir) == "draft"
    plan = json.loads((run_dir / "artifacts" / "retrieval_plan.json").read_text(encoding="utf-8"))
    assert plan.get("plan_complete") is True