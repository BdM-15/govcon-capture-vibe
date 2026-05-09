import asyncio
from pathlib import Path

from src.skills.manager import SkillExecutor
from src.skills.runtime_support import ToolLoopResult
from src.skills.runs import SkillRunStore
from src.skills.skill_catalog import SkillCatalog
from src.skills.skill_models import Skill, SkillFrontmatter, SkillInvocationResult
from src.skills.skill_tools_runner import run_tools_skill
from src.skills.tool_filesystem import tool_promote_global_note, tool_write_global_note


def _skill(tmp_path: Path, *, runtime: str) -> Skill:
    skill_dir = tmp_path / runtime
    skill_dir.mkdir()
    return Skill(
        name=f"demo-{runtime}",
        path=str(skill_dir),
        skill_md_path=str(skill_dir / "SKILL.md"),
        frontmatter=SkillFrontmatter(
            name=f"demo-{runtime}",
            description="desc",
            metadata={"runtime": runtime},
        ),
        body_md="body",
    )


class FakeCatalog:
    def __init__(self, skill: Skill | None):
        self.skill = skill
        self.touched: list[str] = []

    def get_skill(self, name: str):
        if self.skill and self.skill.name == name:
            return self.skill
        return None

    def touch_invocation(self, name: str) -> None:
        self.touched.append(name)


class MultiCatalog:
    def __init__(self, skills: list[Skill]):
        self.skills = {skill.name: skill for skill in skills}
        self.touched: list[str] = []

    def get_skill(self, name: str):
        return self.skills.get(name)

    def touch_invocation(self, name: str) -> None:
        self.touched.append(name)


def _result(name: str) -> SkillInvocationResult:
    return SkillInvocationResult(
        skill=name,
        workspace="ws",
        response="ok",
        entities_used=[],
        warnings=[],
        elapsed_ms=1,
        prompt_tokens_estimate=1,
        run_id="run-1",
        run_dir="run-dir",
    )


def test_skill_executor_uses_tools_runner_for_tools_mode(tmp_path: Path) -> None:
    skill = _skill(tmp_path, runtime="tools")
    catalog = FakeCatalog(skill)
    captured = {}

    async def fake_tools_runner(**kwargs):
        captured.update(kwargs)
        kwargs["touch_invocation"](kwargs["skill"].name)
        return _result(kwargs["skill"].name)

    executor = SkillExecutor(
        catalog=catalog,  # type: ignore[arg-type]
        run_store=SkillRunStore(),
        mcp_registry=object(),
        tools_runner=fake_tools_runner,
    )

    result = asyncio.run(
        executor.invoke(
            skill.name,
            workspace="ws",
            user_prompt="answer",
            entity_payload={},
            llm=lambda prompt: None,
            workspace_root=tmp_path,
        )
    )

    assert result.skill == skill.name
    assert captured["skill"].name == skill.name
    assert captured["workspace"] == "ws"
    assert catalog.touched == [skill.name]


def test_skill_executor_wires_invoke_skill_child_tool(tmp_path: Path) -> None:
    parent = _skill(tmp_path, runtime="tools")
    child_dir = tmp_path / "child-tools"
    child_dir.mkdir()
    child = Skill(
        name="child-tools",
        path=str(child_dir),
        skill_md_path=str(child_dir / "SKILL.md"),
        frontmatter=SkillFrontmatter(
            name="child-tools",
            description="desc",
            metadata={"runtime": "tools"},
        ),
        body_md="child body",
    )
    catalog = MultiCatalog([parent, child])
    captured = {}

    async def fake_tools_runner(**kwargs):
        skill = kwargs["skill"]
        kwargs["touch_invocation"]("child-tools" if skill.name == "child-tools" else skill.name)
        if skill.name == parent.name:
            tool_result = await kwargs["invoke_skill_fn"](
                "child-tools",
                "render this",
                {"source": "parent"},
            )
            captured["tool_payload"] = tool_result.payload
            captured["tool_extra"] = tool_result.transcript_extra
            return _result(parent.name)
        captured["child_prompt"] = kwargs["user_prompt"]
        return _result(child.name)

    executor = SkillExecutor(
        catalog=catalog,  # type: ignore[arg-type]
        run_store=SkillRunStore(),
        mcp_registry=object(),
        tools_runner=fake_tools_runner,
    )

    result = asyncio.run(
        executor.invoke(
            parent.name,
            workspace="ws",
            user_prompt="answer",
            entity_payload={},
            llm=lambda prompt: None,
            workspace_root=tmp_path,
        )
    )

    assert result.skill == parent.name
    assert captured["tool_payload"]["skill"] == "child-tools"
    assert captured["tool_extra"] == {
        "child_skill": "child-tools",
        "child_run_id": "run-1",
        "artifact_count": 0,
    }
    assert "Parent handoff context" in captured["child_prompt"]
    assert '"source": "parent"' in captured["child_prompt"]


def test_skill_executor_uses_legacy_runner_for_legacy_mode(tmp_path: Path) -> None:
    skill = _skill(tmp_path, runtime="legacy")
    catalog = FakeCatalog(skill)
    captured = {}

    async def fake_legacy_runner(**kwargs):
        captured.update(kwargs)
        kwargs["touch_invocation"](kwargs["skill"].name)
        return _result(kwargs["skill"].name)

    async def fake_llm(prompt: str) -> str:
        return prompt

    executor = SkillExecutor(
        catalog=catalog,  # type: ignore[arg-type]
        run_store=SkillRunStore(),
        mcp_registry=object(),
        legacy_runner=fake_legacy_runner,
    )

    result = asyncio.run(
        executor.invoke(
            skill.name,
            workspace="ws",
            user_prompt="answer",
            entity_payload={"entities": {}},
            llm=fake_llm,
            workspace_root=tmp_path,
            max_payload_chars=123,
        )
    )

    assert result.skill == skill.name
    assert captured["skill"].name == skill.name
    assert captured["max_payload_chars"] == 123
    assert callable(captured["persist_run"])
    assert catalog.touched == [skill.name]


def test_skill_executor_raises_for_unknown_skill(tmp_path: Path) -> None:
    executor = SkillExecutor(
        catalog=FakeCatalog(None),  # type: ignore[arg-type]
        run_store=SkillRunStore(),
        mcp_registry=object(),
    )

    try:
        asyncio.run(
            executor.invoke(
                "missing",
                workspace="ws",
                user_prompt="answer",
                entity_payload={},
                llm=lambda prompt: None,
                workspace_root=tmp_path,
            )
        )
    except KeyError as exc:
        assert "Unknown skill" in str(exc)
    else:
        raise AssertionError("expected KeyError for missing skill")


def test_phase_promoter_tools_mode_smoke_writes_global_and_workspace_targets(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    catalog = SkillCatalog(
        skills_dir=repo_root / ".github" / "skills",
        ledger_path=tmp_path / "skills.json",
    )
    skill = catalog.get_skill("phase-promoter")
    assert skill is not None

    workspace_root = tmp_path / "rag_storage" / "demo"
    workspace_root.mkdir(parents=True)
    store = SkillRunStore()

    async def fake_tool_loop(**kwargs):
        ctx = kwargs["ctx"]
        content = (
            "---\n"
            "date: 2026-05-09\n"
            "source: synth\n"
            "status: evergreen\n"
            "tags: [meta]\n"
            "derives_from: inbox/2026-05-09-demo.md\n"
            "---\n\n"
            "Durable note\n"
        )
        await tool_write_global_note(ctx, "notes/2026-05-09-demo-evergreen.md", content)
        await tool_promote_global_note(ctx, "notes/2026-05-09-demo-evergreen.md")
        return ToolLoopResult(
            response="wrote real targets",
            transcript=[],
            turns=1,
            tool_calls=2,
            finish_reason="stop",
            usage_total={"total_tokens": 0},
            warnings=[],
        )

    result = asyncio.run(
        run_tools_skill(
            skill=skill,
            workspace="demo",
            user_prompt="Promote this note.",
            workspace_root=workspace_root,
            slice_fn=None,
            retrieve_fn=None,
            run_store=store,
            mcp_registry=object(),
            touch_invocation=lambda _name: None,
            run_tool_loop_fn=fake_tool_loop,
        )
    )

    global_note = tmp_path / "global" / "notes" / "2026-05-09-demo-evergreen.md"
    workspace_note = tmp_path / "rag_storage" / "demo" / "sources" / "2026-05-09-demo-evergreen.md"
    assert result.skill == "phase-promoter"
    assert global_note.is_file()
    assert workspace_note.is_file()
    assert workspace_note.read_text(encoding="utf-8") == global_note.read_text(encoding="utf-8")


def test_global_idea_capturer_tools_mode_smoke_writes_real_inbox_note(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    catalog = SkillCatalog(
        skills_dir=repo_root / ".github" / "skills",
        ledger_path=tmp_path / "skills.json",
    )
    skill = catalog.get_skill("global-idea-capturer")
    assert skill is not None

    workspace_root = tmp_path / "rag_storage" / "demo"
    workspace_root.mkdir(parents=True)
    store = SkillRunStore()

    async def fake_tool_loop(**kwargs):
        ctx = kwargs["ctx"]
        content = (
            "---\n"
            "date: 2026-05-09\n"
            "source: capture\n"
            "status: inbox\n"
            "tags: [meta, pricing]\n"
            "workspace: demo\n"
            "---\n\n"
            "Capture this thought verbatim\n"
        )
        await tool_write_global_note(ctx, "inbox/2026-05-09-demo-capture.md", content)
        return ToolLoopResult(
            response="Captured -> global/inbox/2026-05-09-demo-capture.md",
            transcript=[],
            turns=1,
            tool_calls=1,
            finish_reason="stop",
            usage_total={"total_tokens": 0},
            warnings=[],
        )

    result = asyncio.run(
        run_tools_skill(
            skill=skill,
            workspace="demo",
            user_prompt="Capture this thought.",
            workspace_root=workspace_root,
            slice_fn=None,
            retrieve_fn=None,
            run_store=store,
            mcp_registry=object(),
            touch_invocation=lambda _name: None,
            run_tool_loop_fn=fake_tool_loop,
        )
    )

    inbox_note = tmp_path / "global" / "inbox" / "2026-05-09-demo-capture.md"
    assert result.skill == "global-idea-capturer"
    assert inbox_note.is_file()
    assert "status: inbox" in inbox_note.read_text(encoding="utf-8")