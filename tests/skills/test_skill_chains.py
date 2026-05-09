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
                        products=["obligation_data"],
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
    assert "obligation_data" in result.steps["intel"].artifacts[0]["products"]
    assert result.steps["ptw"].input_artifacts[0].filename == "competitive-intel.json"
    assert Path(result.steps["ptw"].input_artifacts[0].path).as_posix().endswith(
        "artifacts/competitive-intel.json"
    )
    assert "obligation_data" in result.steps["ptw"].input_artifacts[0].products
    assert "upstream_steps" in calls[1][1]
    assert "competitive-intel.json" in calls[1][1]
    expected_artifact_path = str(
        Path(result.steps["intel"].run_dir) / "artifacts" / "competitive-intel.json"
    )
    handoff_json = calls[1][1].split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    handoff = json.loads(handoff_json)
    assert handoff["input_artifacts"][0]["path"] == expected_artifact_path
    assert "Use input_artifacts[].path when a tool needs an upstream file path" in calls[1][1]
    persisted = store.get_chain_run(tmp_path, result.chain_id)
    assert persisted is not None
    assert persisted["status"] == "completed"


def test_chain_executor_passes_capture_artifact_into_phase_promoter(tmp_path: Path) -> None:
    asyncio.run(_chain_executor_passes_capture_artifact_into_phase_promoter(tmp_path))


async def _chain_executor_passes_capture_artifact_into_phase_promoter(tmp_path: Path) -> None:
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
        artifacts_dir = run_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        artifact_name = "captured-note.md" if name == "global-idea-capturer" else "evergreen-note.md"
        (artifacts_dir / artifact_name).write_text(f"artifact for {name}", encoding="utf-8")
        return _fake_result(name, run_id, run_dir, prompt)

    executor = SkillChainExecutor(invoke_skill=invoke_skill, run_store=store)
    spec = ChainSpec(
        name="capture-to-promotion",
        steps=[
            ChainStepSpec(id="capture", skill="global-idea-capturer", prompt="Capture the note."),
            ChainStepSpec(
                id="promote",
                skill="phase-promoter",
                prompt="Promote the durable parts.",
                depends_on=["capture"],
                artifact_requirements=[
                    ChainArtifactRequirement(
                        id="capture-note",
                        from_steps=["capture"],
                        products=["inbox_note"],
                        extensions=["md"],
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
        entity_payload={},
    )

    assert result.status == "completed"
    assert [call[0] for call in calls] == ["global-idea-capturer", "phase-promoter"]
    assert [artifact.filename for artifact in result.steps["promote"].input_artifacts] == [
        "captured-note.md"
    ]
    assert result.steps["promote"].input_artifacts[0].products == ["inbox_note"]
    assert "captured-note.md" in calls[1][1]
    assert "Use input_artifacts[].path when a tool needs an upstream file path" in calls[1][1]


def test_chain_executor_passes_note_preview_and_connection_guidance_into_grill_me(
    tmp_path: Path,
) -> None:
    asyncio.run(_chain_executor_passes_note_preview_and_connection_guidance_into_grill_me(tmp_path))


async def _chain_executor_passes_note_preview_and_connection_guidance_into_grill_me(
    tmp_path: Path,
) -> None:
    store = SkillRunStore()
    calls: list[tuple[str, str]] = []
    retrieval_calls: list[tuple[str, str, str, int]] = []

    async def fake_retrieve(query: str, skill_description: str, mode: str, top_k: int) -> dict[str, Any]:
        retrieval_calls.append((query, skill_description, mode, top_k))
        return {
            "names": {"Appendix H", "Staffing Model"},
            "chunk_ids": {"chunk-7", "chunk-2"},
            "metadata": {"used": True},
        }

    async def invoke_skill(name: str, **kwargs: Any) -> SkillInvocationResult:
        prompt = kwargs["user_prompt"]
        calls.append((name, prompt))
        run_id, run_dir = store.create_run_dir(
            workspace_root=kwargs["workspace_root"],
            skill_name=name,
            user_prompt=prompt,
            started_at=datetime.now(timezone.utc),
        )
        artifacts_dir = run_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        if name == "global-idea-capturer":
            (artifacts_dir / "captured-note.md").write_text(
                "# Brain dump\n\nNeed connect workload spike to Appendix H staffing model.",
                encoding="utf-8",
            )
        return _fake_result(name, run_id, run_dir, prompt)

    executor = SkillChainExecutor(invoke_skill=invoke_skill, run_store=store)
    spec = ChainSpec(
        name="capture-to-grill",
        prompt="Capture this note and find stronger workspace connections and wikilinks.",
        context={"expected_outcome": "Questions that deepen wiki links"},
        steps=[
            ChainStepSpec(id="capture", skill="global-idea-capturer", prompt="Capture the note."),
            ChainStepSpec(
                id="grill",
                skill="grill-me",
                prompt="Stress-test connections.",
                depends_on=["capture"],
                artifact_requirements=[
                    ChainArtifactRequirement(
                        id="capture-note",
                        from_steps=["capture"],
                        products=["inbox_note"],
                        extensions=["md"],
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
        entity_payload={},
        retrieve_fn=fake_retrieve,
    )

    assert result.status == "completed"
    assert [call[0] for call in calls] == ["global-idea-capturer", "grill-me"]
    grill_prompt = calls[1][1]
    assert "Use captured-note content to surface missing wiki/workspace links" in grill_prompt
    assert "## Workspace Connection Candidates" in grill_prompt
    assert "Appendix H" in grill_prompt
    assert "Staffing Model" in grill_prompt
    assert "chunk-2" in grill_prompt
    assert "Need connect workload spike to Appendix H staffing model." in grill_prompt
    assert "captured-note.md" in grill_prompt
    assert retrieval_calls == [
        (
            retrieval_calls[0][0],
            "Find candidate workspace/wiki links for this captured note.",
            "hybrid",
            8,
        )
    ]
    assert "Need connect workload spike to Appendix H staffing model." in retrieval_calls[0][0]


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


def test_chain_executor_matches_artifact_products_before_extension(tmp_path: Path) -> None:
    asyncio.run(_chain_executor_matches_artifact_products_before_extension(tmp_path))


async def _chain_executor_matches_artifact_products_before_extension(tmp_path: Path) -> None:
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
        if name == "competitive-intel":
            (run_dir / "artifacts" / "raw.json").write_text("{}", encoding="utf-8")
            (run_dir / "artifacts" / "obligations.json").write_text("{}", encoding="utf-8")
            (run_dir / "artifacts_manifest.json").write_text(
                json.dumps(
                    {
                        "raw.json": {"products": ["scratch_data"]},
                        "obligations.json": {"products": ["obligation_data"]},
                    }
                ),
                encoding="utf-8",
            )
        return _fake_result(name, run_id, run_dir, kwargs["user_prompt"])

    executor = SkillChainExecutor(invoke_skill=invoke_skill, run_store=store)
    spec = ChainSpec(
        name="product-contract-chain",
        steps=[
            ChainStepSpec(id="intel", skill="competitive-intel"),
            ChainStepSpec(
                id="ptw",
                skill="price-to-win",
                depends_on=["intel"],
                artifact_requirements=[
                    ChainArtifactRequirement(
                        id="obligation-data",
                        from_steps=["intel"],
                        products=["obligation_data"],
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
        entity_payload={},
    )

    assert result.status == "completed"
    assert calls == ["competitive-intel", "price-to-win"]
    assert [ref.filename for ref in result.steps["ptw"].input_artifacts] == [
        "obligations.json"
    ]


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


def test_chain_executor_resume_includes_resume_notes_in_prompt(tmp_path: Path) -> None:
    asyncio.run(_chain_executor_resume_includes_resume_notes_in_prompt(tmp_path))


async def _chain_executor_resume_includes_resume_notes_in_prompt(tmp_path: Path) -> None:
    store = SkillRunStore()
    prompts: list[tuple[str, str]] = []
    ptw_attempts = 0

    async def invoke_skill(name: str, **kwargs: Any) -> SkillInvocationResult:
        nonlocal ptw_attempts
        prompt = kwargs["user_prompt"]
        prompts.append((name, prompt))
        if name == "price-to-win":
            ptw_attempts += 1
            if ptw_attempts == 1:
                raise RuntimeError("first PTW attempt failed")
        run_id, run_dir = store.create_run_dir(
            workspace_root=kwargs["workspace_root"],
            skill_name=name,
            user_prompt=prompt,
            started_at=datetime.now(timezone.utc),
        )
        return _fake_result(name, run_id, run_dir, prompt)

    executor = SkillChainExecutor(invoke_skill=invoke_skill, run_store=store)
    spec = ChainSpec(
        name="resume-chain-with-notes",
        steps=[
            ChainStepSpec(id="intel", skill="competitive-intel"),
            ChainStepSpec(id="ptw", skill="price-to-win", depends_on=["intel"]),
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
        resume_notes="Incumbent PIID is FA1234-56-D-7890.",
    )

    ptw_prompts = [prompt for name, prompt in prompts if name == "price-to-win"]
    assert len(ptw_prompts) == 2
    assert "## User-Supplied Missing Input" in ptw_prompts[1]
    assert "Incumbent PIID is FA1234-56-D-7890." in ptw_prompts[1]
    assert resumed.resume_notes == "Incumbent PIID is FA1234-56-D-7890."


def test_chain_executor_marks_partial_when_expected_output_missing(tmp_path: Path) -> None:
    asyncio.run(_chain_executor_marks_partial_when_expected_output_missing(tmp_path))


async def _chain_executor_marks_partial_when_expected_output_missing(tmp_path: Path) -> None:
    store = SkillRunStore()

    async def invoke_skill(name: str, **kwargs: Any) -> SkillInvocationResult:
        run_id, run_dir = store.create_run_dir(
            workspace_root=kwargs["workspace_root"],
            skill_name=name,
            user_prompt=kwargs["user_prompt"],
            started_at=datetime.now(timezone.utc),
        )
        artifacts_dir = run_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        (artifacts_dir / "brief.docx").write_bytes(b"docx")
        (artifacts_dir / "report.json").write_text("{}", encoding="utf-8")
        (run_dir / "artifacts_manifest.json").write_text(
            json.dumps(
                {
                    "report.json": {
                        "render_status": "failed",
                        "render_targets": ["price_to_win_workbook.xlsx"],
                        "render_message": "xlsx render failed",
                    }
                }
            ),
            encoding="utf-8",
        )
        return SkillInvocationResult(
            skill=name,
            workspace="test-workspace",
            response=(
                "**GAP IDENTIFIED - Cannot fully satisfy quality gate.**\n\n"
                "**Exact gaps (per quality gate):**\n"
                "- Missing incumbent PIID\n"
                "- No workload spreadsheet\n"
            ),
            entities_used=[],
            warnings=[],
            elapsed_ms=9,
            prompt_tokens_estimate=0,
            run_id=run_id,
            run_dir=str(run_dir),
            finish_reason="stop",
        )

    executor = SkillChainExecutor(invoke_skill=invoke_skill, run_store=store)
    spec = ChainSpec(
        name="render-chain",
        context={"expected_outcome": "Excel workbook and brief"},
        steps=[ChainStepSpec(id="render", skill="renderers")],
    )

    result = await executor.invoke(
        spec,
        workspace="test-workspace",
        workspace_root=tmp_path,
        llm=_noop_llm,
        entity_payload={},
    )

    assert result.status == "partial"
    assert result.steps["render"].status == "partial"
    assert result.steps["render"].missing_inputs == [
        "Missing incumbent PIID",
        "No workload spreadsheet",
    ]
    assert result.missing_outputs == ["xlsx"]
    assert [artifact.filename for artifact in result.promoted_artifacts] == ["brief.docx"]
    assert result.input_request == {
        "needed": True,
        "step_id": "render",
        "skill": "renderers",
        "missing_inputs": ["Missing incumbent PIID", "No workload spreadsheet"],
        "resume_step_id": "render",
    }


def test_chain_executor_allows_downstream_after_partial_upstream(tmp_path: Path) -> None:
    asyncio.run(_chain_executor_allows_downstream_after_partial_upstream(tmp_path))


async def _chain_executor_allows_downstream_after_partial_upstream(tmp_path: Path) -> None:
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
        (run_dir / "artifacts" / f"{name}.json").write_text("{}", encoding="utf-8")
        response = "ok"
        if name == "competitive-intel":
            response = (
                "**GAP IDENTIFIED - Cannot fully satisfy quality gate.**\n\n"
                "**Exact gaps (per quality gate):**\n"
                "- Missing PIID\n"
            )
        return SkillInvocationResult(
            skill=name,
            workspace="test-workspace",
            response=response,
            entities_used=[],
            warnings=[],
            elapsed_ms=5,
            prompt_tokens_estimate=0,
            run_id=run_id,
            run_dir=str(run_dir),
            finish_reason="stop",
        )

    executor = SkillChainExecutor(invoke_skill=invoke_skill, run_store=store)
    spec = ChainSpec(
        name="partial-upstream-chain",
        steps=[
            ChainStepSpec(id="intel", skill="competitive-intel"),
            ChainStepSpec(id="ptw", skill="price-to-win", depends_on=["intel"]),
        ],
    )

    result = await executor.invoke(
        spec,
        workspace="test-workspace",
        workspace_root=tmp_path,
        llm=_noop_llm,
        entity_payload={},
    )

    assert calls == ["competitive-intel", "price-to-win"]
    assert result.steps["intel"].status == "partial"
    assert result.steps["ptw"].status == "completed"
    assert result.status == "partial"


def test_chain_spec_rejects_unknown_or_later_dependencies() -> None:
    with pytest.raises(ValidationError):
        ChainSpec(
            name="bad-chain",
            steps=[
                ChainStepSpec(id="ptw", skill="price-to-win", depends_on=["intel"]),
                ChainStepSpec(id="intel", skill="competitive-intel"),
            ],
        )
