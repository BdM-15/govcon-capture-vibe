"""Tests for LangGraph eval retrieve -> finalize -> retry pipeline."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from src.skills.chain_executor import SkillChainExecutor
from src.skills.chain_models import ChainRunState, ChainSpec, ChainStepRun, ChainStepSpec
from src.skills.graphs.eval_pipeline_graph import run_eval_pipeline_step
from src.skills.runs import SkillRunStore
from src.skills.skill_models import SkillInvocationResult


async def _noop_llm(prompt: str) -> str:
    return prompt


def test_eval_pipeline_passes_after_platform_finalize(tmp_path: Path) -> None:
    asyncio.run(_eval_pipeline_passes_after_platform_finalize(tmp_path))


async def _eval_pipeline_passes_after_platform_finalize(tmp_path: Path) -> None:
    store = SkillRunStore()

    async def invoke_skill(name: str, **kwargs: Any) -> SkillInvocationResult:
        run_id, run_dir = store.create_run_dir(
            workspace_root=kwargs["workspace_root"],
            skill_name=name,
            user_prompt=kwargs["user_prompt"],
            started_at=datetime.now(timezone.utc),
        )
        artifacts = Path(run_dir) / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "eval_handoff.json").write_text(
            json.dumps({"eval_crosswalk": [{"evaluation_factor": "F1"}], "claim_gaps": []}),
            encoding="utf-8",
        )
        return SkillInvocationResult(
            skill=name,
            workspace="test",
            response="eval retrieve complete",
            entities_used=[],
            warnings=[],
            elapsed_ms=12,
            prompt_tokens_estimate=0,
            run_id=run_id,
            run_dir=str(run_dir),
            finish_reason="stop",
        )

    executor = SkillChainExecutor(invoke_skill=invoke_skill, run_store=store)
    chain_dir = tmp_path / "skill_chains" / "chain-eval-test"
    chain_dir.mkdir(parents=True)

    spec = ChainSpec(
        name="eval-only",
        prompt="test",
        steps=[ChainStepSpec(id="eval", skill="readiness-frame-eval", prompt="e")],
    )
    chain = ChainRunState(
        chain_id="chain-eval-test",
        workspace="test-workspace",
        status="running",
        spec=spec,
        steps={"eval": ChainStepRun(id="eval", skill="readiness-frame-eval", status="running")},
    )

    step = spec.steps[0]
    step = step.model_copy(
        update={
            "context": {
                "langgraph_eval_pipeline": True,
                "eval_retrieve_only": True,
            }
        }
    )

    with patch(
        "src.skills.graphs.eval_pipeline_graph.finalize_eval_handoff",
        new_callable=AsyncMock,
        return_value={
            "passed": True,
            "issues": [],
            "blocking_issues": [],
            "retriable_issues": [],
            "warnings": [],
        },
    ):
        outcome = await run_eval_pipeline_step(
            chain=chain,
            step=step,
            chain_dir=chain_dir,
            executor=executor,
            workspace_root=tmp_path,
            entity_payload={},
            llm=_noop_llm,
        )

    assert outcome.error == ""
    assert outcome.result is not None
    assert outcome.result.finish_reason == "stop"


def test_eval_pipeline_retries_on_retriable_gate(tmp_path: Path) -> None:
    asyncio.run(_eval_pipeline_retries_on_retriable_gate(tmp_path))


async def _eval_pipeline_retries_on_retriable_gate(tmp_path: Path) -> None:
    store = SkillRunStore()
    retrieve_calls = 0

    async def invoke_skill(name: str, **kwargs: Any) -> SkillInvocationResult:
        nonlocal retrieve_calls
        retrieve_calls += 1
        run_id, run_dir = store.create_run_dir(
            workspace_root=kwargs["workspace_root"],
            skill_name=name,
            user_prompt=kwargs["user_prompt"],
            started_at=datetime.now(timezone.utc),
        )
        artifacts = Path(run_dir) / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "eval_handoff.json").write_text(
            json.dumps({"eval_crosswalk": [], "claim_gaps": []}),
            encoding="utf-8",
        )
        return SkillInvocationResult(
            skill=name,
            workspace="test",
            response="partial",
            entities_used=[],
            warnings=[],
            elapsed_ms=5,
            prompt_tokens_estimate=0,
            run_id=run_id,
            run_dir=str(run_dir),
            finish_reason="stop",
        )

    executor = SkillChainExecutor(invoke_skill=invoke_skill, run_store=store)
    chain_dir = tmp_path / "skill_chains" / "chain-eval-retry"
    chain_dir.mkdir(parents=True)

    step = ChainStepSpec(
        id="eval",
        skill="readiness-frame-eval",
        prompt="e",
        context={"langgraph_eval_pipeline": True, "eval_retrieve_only": True},
    )
    spec = ChainSpec(name="eval-only", prompt="test", steps=[step])
    chain = ChainRunState(
        chain_id="chain-eval-retry",
        workspace="test-workspace",
        status="running",
        spec=spec,
        steps={"eval": ChainStepRun(id="eval", skill="readiness-frame-eval", status="running")},
    )

    finalize_results = [
        {
            "passed": False,
            "issues": ["coverage: 2/24 rows"],
            "blocking_issues": [],
            "retriable_issues": ["coverage: 2/24 rows"],
            "warnings": [],
        },
        {
            "passed": True,
            "issues": [],
            "blocking_issues": [],
            "retriable_issues": [],
            "warnings": [],
        },
    ]

    with patch(
        "src.skills.graphs.eval_pipeline_graph.finalize_eval_handoff",
        new_callable=AsyncMock,
        side_effect=finalize_results,
    ):
        outcome = await run_eval_pipeline_step(
            chain=chain,
            step=step,
            chain_dir=chain_dir,
            executor=executor,
            workspace_root=tmp_path,
            entity_payload={},
            llm=_noop_llm,
        )

    assert outcome.result is not None
    assert retrieve_calls == 2