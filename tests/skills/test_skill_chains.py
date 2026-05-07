from __future__ import annotations

import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.skills.chain_executor import SkillChainExecutor
from src.skills.chain_models import ChainArtifactRequirement, ChainSpec, ChainStepSpec
from src.skills.runs import SkillRunStore
from src.skills.skill_models import SkillInvocationResult


async def _noop_llm(prompt: str) -> str:
    return prompt


def _fake_result(skill: str, run_id: str, run_dir: Path, prompt: str) -> SkillInvocationResult:
    return SkillInvocationResult(
        skill=skill,
        workspace="test-workspace",
        response=f"response for {skill}: {prompt[:20]}",
        entities_used=[],
        warnings=[],
        elapsed_ms=7,
        prompt_tokens_estimate=0,
        run_id=run_id,
        run_dir=str(run_dir),
        finish_reason="stop",
    )


def test_chain_executor_runs_steps_and_persists_state(tmp_path: Path) -> None:
    asyncio.run(_chain_executor_runs_steps_and_persists_state(tmp_path))


async def _chain_executor_runs_steps_and_persists_state(tmp_path: Path) -> None:
    store = SkillRunStore()
    calls: list[tuple[str, str]] = []

    async def invoke_skill(name: str, **kwargs: Any) -> SkillInvocationResult:
        prompt = kwargs["user_prompt"]
        calls.append((name, prompt))
        run_id, run_dir = store.create_run_dir(
            workspace_root=kwargs["workspace_root"],
            skill_name=name,
            user_prompt=prompt,
            started_at=datetime.now(timezone.utc),
        )
        (run_dir / "artifacts" / f"{name}.json").write_text(
            json.dumps({"skill": name}),
            encoding="utf-8",
        )
        return _fake_result(name, run_id, run_dir, prompt)

    executor = SkillChainExecutor(invoke_skill=invoke_skill, run_store=store)
    spec = ChainSpec(
        name="intel-to-price",
        prompt="Build a chained deliverable.",
        steps=[
            ChainStepSpec(id="intel", skill="competitive-intel", prompt="Find incumbent intel."),
            ChainStepSpec(
                id="ptw",
                skill="price-to-win",
                prompt="Use prior intel for PTW.",
                depends_on=["intel"],
                artifact_requirements=[
                    ChainArtifactRequirement(
                        id="intel-json",
                        from_steps=["intel"],
                        extensions=["json"],
                    )
                ],
            ),
        ],
    )

    result = await executor.invoke(
        spec,
        workspace="test-workspace",
        workspace_root=tmp_path,
        llm=_noop_llm,
        entity_payload={"entities": {}},
    )

    assert result.status == "completed"
    assert [call[0] for call in calls] == ["competitive-intel", "price-to-win"]
    assert result.steps["intel"].status == "completed"
    assert result.steps["ptw"].status == "completed"
    assert result.steps["intel"].artifacts[0]["name"] == "competitive-intel.json"
    assert result.steps["ptw"].input_artifacts[0].filename == "competitive-intel.json"
    assert "upstream_steps" in calls[1][1]
    assert "competitive-intel.json" in calls[1][1]
    persisted = store.get_chain_run(tmp_path, result.chain_id)
    assert persisted is not None
    assert persisted["status"] == "completed"


def test_chain_executor_stops_after_failed_step(tmp_path: Path) -> None:
    asyncio.run(_chain_executor_stops_after_failed_step(tmp_path))


async def _chain_executor_stops_after_failed_step(tmp_path: Path) -> None:
    store = SkillRunStore()
    calls: list[str] = []

    async def invoke_skill(name: str, **kwargs: Any) -> SkillInvocationResult:
        calls.append(name)
        if name == "price-to-win":
            raise RuntimeError("rate data unavailable")
        run_id, run_dir = store.create_run_dir(
            workspace_root=kwargs["workspace_root"],
            skill_name=name,
            user_prompt=kwargs["user_prompt"],
            started_at=datetime.now(timezone.utc),
        )
        return _fake_result(name, run_id, run_dir, kwargs["user_prompt"])

    executor = SkillChainExecutor(invoke_skill=invoke_skill, run_store=store)
    spec = ChainSpec(
        name="failure-chain",
        steps=[
            ChainStepSpec(id="intel", skill="competitive-intel"),
            ChainStepSpec(id="ptw", skill="price-to-win", depends_on=["intel"]),
            ChainStepSpec(id="brief", skill="proposal-generator", depends_on=["ptw"]),
        ],
    )

    result = await executor.invoke(
        spec,
        workspace="test-workspace",
        workspace_root=tmp_path,
        llm=_noop_llm,
        entity_payload={},
    )

    assert result.status == "failed"
    assert calls == ["competitive-intel", "price-to-win"]
    assert result.steps["ptw"].status == "failed"
    assert result.steps["brief"].status == "skipped"
    assert "rate data unavailable" in result.error


def test_chain_executor_fails_missing_artifact_contract(tmp_path: Path) -> None:
    asyncio.run(_chain_executor_fails_missing_artifact_contract(tmp_path))


async def _chain_executor_fails_missing_artifact_contract(tmp_path: Path) -> None:
    store = SkillRunStore()
    calls: list[str] = []

    async def invoke_skill(name: str, **kwargs: Any) -> SkillInvocationResult:
        calls.append(name)
        run_id, run_dir = store.create_run_dir(
            workspace_root=kwargs["workspace_root"],
            skill_name=name,
            user_prompt=kwargs["user_prompt"],
            started_at=datetime.now(timezone.utc),
        )
        (run_dir / "artifacts" / "intel.md").write_text("intel", encoding="utf-8")
        return _fake_result(name, run_id, run_dir, kwargs["user_prompt"])

    executor = SkillChainExecutor(invoke_skill=invoke_skill, run_store=store)
    spec = ChainSpec(
        name="missing-contract-chain",
        steps=[
            ChainStepSpec(id="intel", skill="competitive-intel"),
            ChainStepSpec(
                id="ptw",
                skill="price-to-win",
                depends_on=["intel"],
                artifact_requirements=[
                    ChainArtifactRequirement(id="workbook", extensions=["xlsx"])
                ],
            ),
        ],
    )

    result = await executor.invoke(
        spec,
        workspace="test-workspace",
        workspace_root=tmp_path,
        llm=_noop_llm,
        entity_payload={},
    )

    assert result.status == "failed"
    assert calls == ["competitive-intel"]
    assert result.steps["ptw"].status == "failed"
    assert "artifact requirement workbook" in result.steps["ptw"].error


def test_chain_executor_resume_preserves_completed_steps(tmp_path: Path) -> None:
    asyncio.run(_chain_executor_resume_preserves_completed_steps(tmp_path))


async def _chain_executor_resume_preserves_completed_steps(tmp_path: Path) -> None:
    store = SkillRunStore()
    calls: list[str] = []
    ptw_attempts = 0

    async def invoke_skill(name: str, **kwargs: Any) -> SkillInvocationResult:
        nonlocal ptw_attempts
        calls.append(name)
        if name == "price-to-win":
            ptw_attempts += 1
            if ptw_attempts == 1:
                raise RuntimeError("first PTW attempt failed")
        run_id, run_dir = store.create_run_dir(
            workspace_root=kwargs["workspace_root"],
            skill_name=name,
            user_prompt=kwargs["user_prompt"],
            started_at=datetime.now(timezone.utc),
        )
        return _fake_result(name, run_id, run_dir, kwargs["user_prompt"])

    executor = SkillChainExecutor(invoke_skill=invoke_skill, run_store=store)
    spec = ChainSpec(
        name="resume-chain",
        steps=[
            ChainStepSpec(id="intel", skill="competitive-intel"),
            ChainStepSpec(id="ptw", skill="price-to-win", depends_on=["intel"]),
            ChainStepSpec(id="brief", skill="proposal-generator", depends_on=["ptw"]),
        ],
    )

    failed = await executor.invoke(
        spec,
        workspace="test-workspace",
        workspace_root=tmp_path,
        llm=_noop_llm,
        entity_payload={},
    )
    resumed = await executor.resume(
        failed,
        workspace_root=tmp_path,
        llm=_noop_llm,
        entity_payload={},
    )

    assert resumed.status == "completed"
    assert calls == [
        "competitive-intel",
        "price-to-win",
        "price-to-win",
        "proposal-generator",
    ]
    assert resumed.steps["intel"].run_id == failed.steps["intel"].run_id


def test_chain_spec_rejects_unknown_or_later_dependencies() -> None:
    with pytest.raises(ValidationError):
        ChainSpec(
            name="bad-chain",
            steps=[
                ChainStepSpec(id="ptw", skill="price-to-win", depends_on=["intel"]),
                ChainStepSpec(id="intel", skill="competitive-intel"),
            ],
        )
