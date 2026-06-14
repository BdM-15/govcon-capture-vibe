"""Tests for LangGraph chain runner routing and events."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from src.skills.chain_models import ChainSpec, ChainStepSpec
from src.skills.graphs.chain_events import read_chain_events
from src.skills.graphs.langgraph_chain_runner import LangGraphChainRunner, use_langgraph_for_spec
from src.skills.mission_readiness_chain import build_mission_readiness_chain_spec
from src.skills.readiness_solo_invoke import build_readiness_solo_chain_spec
from src.skills.runs import SkillRunStore
from src.skills.skill_models import SkillInvocationResult


async def _noop_llm(prompt: str) -> str:
    return prompt


def test_use_langgraph_for_mission_readiness_preset() -> None:
    spec = build_mission_readiness_chain_spec("Build MRF.")
    assert use_langgraph_for_spec(spec) is True
    solo = build_readiness_solo_chain_spec("workload", "Build MRF.")
    assert use_langgraph_for_spec(solo) is True
    other = ChainSpec(name="x", prompt="y", steps=[ChainStepSpec(id="a", skill="b", prompt="c")])
    assert use_langgraph_for_spec(other) is False


def test_langgraph_runner_emits_events(tmp_path: Path) -> None:
    asyncio.run(_langgraph_runner_emits_events(tmp_path))


async def _langgraph_runner_emits_events(tmp_path: Path) -> None:
    store = SkillRunStore()

    async def invoke_skill(name: str, **kwargs: Any) -> SkillInvocationResult:
        run_id, run_dir = store.create_run_dir(
            workspace_root=kwargs["workspace_root"],
            skill_name=name,
            user_prompt=kwargs["user_prompt"],
            started_at=datetime.now(timezone.utc),
        )
        artifacts = run_dir / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        handoff_name = {
            "readiness-frame-eval": "eval_handoff.json",
            "readiness-frame-workload": "workload_handoff.json",
        }.get(name)
        if handoff_name:
            payload = (
                {
                    "eval_crosswalk": [
                        {
                            "factor": "Factor 1 Management",
                            "evaluation_crosswalk": "Program office evaluates organizational integration for readiness sustainment across all task areas and volumes.",
                            "source_chunk_ids": ["tb-1234567890abcdef"],
                        }
                    ]
                }
                if handoff_name == "eval_handoff.json"
                else {"mission_readiness_frame": {"readiness_outcome": "Ready"}, "claim_gaps": []}
            )
            (artifacts / handoff_name).write_text(
                __import__("json").dumps(payload),
                encoding="utf-8",
            )
        return SkillInvocationResult(
            skill=name,
            workspace="test",
            response=f"{name} complete.",
            entities_used=[],
            warnings=[],
            elapsed_ms=5,
            prompt_tokens_estimate=0,
            run_id=run_id,
            run_dir=str(run_dir),
            finish_reason="stop",
        )

    runner = LangGraphChainRunner(invoke_skill=invoke_skill, run_store=store)
    spec = ChainSpec(
        name="mini-readiness",
        prompt="test",
        context={"preset": "mission-readiness"},
        steps=[
            ChainStepSpec(
                id="eval",
                skill="readiness-frame-eval",
                prompt="e",
                context={"langgraph_step_pipeline": True, "eval_retrieve_only": True},
            ),
            ChainStepSpec(
                id="workload",
                skill="readiness-frame-workload",
                prompt="w",
                context={"langgraph_step_pipeline": True, "eval_retrieve_only": True},
            ),
        ],
    )

    finalize_mock = AsyncMock(
        return_value={
            "passed": True,
            "issues": [],
            "blocking_issues": [],
            "retriable_issues": [],
            "warnings": [],
        }
    )
    with patch(
        "src.skills.graphs.step_pipeline_graph.finalize_step_handoff",
        finalize_mock,
    ):
        result = await runner.invoke(
            spec,
            workspace="test-workspace",
            workspace_root=tmp_path,
            llm=_noop_llm,
            entity_payload={},
        )

    assert result.status in {"completed", "partial"}
    assert finalize_mock.await_count >= 2
    chain_dir = tmp_path / "skill_chains" / result.chain_id
    events = read_chain_events(chain_dir)
    assert any(evt.get("event") == "chain_started" for evt in events)
    assert any(evt.get("event") == "step_finished" for evt in events)