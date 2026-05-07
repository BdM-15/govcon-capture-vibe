import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.skill_routes import register_skill_run_ui_routes
from src.skills.runs import SkillRunStore
from src.skills.skill_emitters import auto_emit_artifacts
from src.skills.skill_models import Skill, SkillFrontmatter
from src.skills.skill_tools_runner import resolve_extra_script_roots, run_tools_skill
from src.skills.tool_types import ToolContext


def _skill(tmp_path: Path) -> Skill:
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "shared-scripts").mkdir()
    return Skill(
        name="demo-skill",
        path=str(skill_dir),
        skill_md_path=str(skill_dir / "SKILL.md"),
        frontmatter=SkillFrontmatter(
            name="demo-skill",
            description="desc",
            metadata={
                "runtime": "tools",
                "mcps": ["demo-mcp"],
                "script_paths": ["shared-scripts", 7, "missing-dir"],
                "auto_emit_artifacts": True,
            },
        ),
        body_md="body",
    )


def test_resolve_extra_script_roots_returns_valid_dirs_and_warnings(tmp_path: Path) -> None:
    skill = _skill(tmp_path)

    roots, warnings = resolve_extra_script_roots(skill)

    assert Path(skill.path) / "shared-scripts" in roots
    assert any(root.as_posix().endswith(".github/skills/renderers/scripts") for root in roots)
    assert any(root.as_posix().endswith(".github/skills/huashu-design/scripts") for root in roots)
    assert any("non-string entry" in warning for warning in warnings)
    assert any("does not exist" in warning for warning in warnings)


def test_run_tools_skill_wires_context_mcp_and_persistence(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    captured = {}
    touched = []
    emitted = []

    class FakeRunStore:
        def create_run_dir(self, **kwargs):
            captured["create_run_dir"] = kwargs
            return "run-1", run_dir

        def persist_tools_run(self, **kwargs):
            captured["persist_tools_run"] = kwargs

    class FakeStartup:
        sessions = {"demo-mcp": object()}
        started_names = ["demo-mcp"]

        @staticmethod
        def warning_messages():
            return ["startup warning"]

    class FakeMCPRegistry:
        def __init__(self):
            self.shutdown_calls = []

        async def start_run_sessions(self, *, run_id, requested):
            captured["start_run_sessions"] = {"run_id": run_id, "requested": requested}
            return FakeStartup()

        async def shutdown_run(self, run_id):
            self.shutdown_calls.append(run_id)

    async def fake_run_tool_loop(**kwargs):
        captured["run_tool_loop"] = kwargs
        assert isinstance(kwargs["ctx"], ToolContext)
        assert kwargs["ctx"].mcp_sessions == {"demo-mcp": FakeStartup.sessions["demo-mcp"]}
        return SimpleNamespace(
            response="done — with smart quotes ‘ok’ and ellipsis…",
            warnings=["loop warning"],
            turns=2,
            tool_calls=3,
            finish_reason="stop",
            usage_total={"total_tokens": 11},
        )

    result = asyncio.run(
        run_tools_skill(
            skill=skill,
            workspace="ws",
            user_prompt="answer",
            workspace_root=tmp_path,
            slice_fn=lambda *args: {},
            retrieve_fn=None,
            run_store=FakeRunStore(),
            mcp_registry=FakeMCPRegistry(),
            touch_invocation=touched.append,
            run_tool_loop_fn=fake_run_tool_loop,
            tool_context_cls=ToolContext,
            auto_emit_fn=lambda skill_arg, run_dir_arg: emitted.append((skill_arg.name, run_dir_arg)),
        )
    )

    assert result.response == "done - with smart quotes 'ok' and ellipsis..."
    assert result.run_id == "run-1"
    assert touched == ["demo-skill"]
    assert emitted == [("demo-skill", run_dir)]
    assert captured["start_run_sessions"] == {"run_id": "run-1", "requested": ["demo-mcp"]}
    assert captured["persist_tools_run"]["response"] == "done - with smart quotes 'ok' and ellipsis..."
    assert captured["persist_tools_run"]["warnings"][0] == "script_paths: skipping non-string entry 7"
    assert "startup warning" in captured["persist_tools_run"]["warnings"]
    assert "loop warning" in captured["persist_tools_run"]["warnings"]


def test_run_tools_skill_auto_emits_by_default(tmp_path: Path) -> None:
    skill_dir = tmp_path / "future-skill"
    skill_dir.mkdir()
    skill = Skill(
        name="future-skill",
        path=str(skill_dir),
        skill_md_path=str(skill_dir / "SKILL.md"),
        frontmatter=SkillFrontmatter(
            name="future-skill",
            description="desc",
            metadata={"runtime": "tools"},
        ),
        body_md="body",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    emitted = []

    class FakeRunStore:
        def create_run_dir(self, **kwargs):
            return "run-1", run_dir

        def persist_tools_run(self, **kwargs):
            pass

    class FakeMCPRegistry:
        async def start_run_sessions(self, *, run_id, requested):
            return SimpleNamespace(sessions={}, started_names=[], warning_messages=lambda: [])

        async def shutdown_run(self, run_id):
            pass

    async def fake_run_tool_loop(**kwargs):
        return SimpleNamespace(
            response="done",
            warnings=[],
            turns=1,
            tool_calls=0,
            finish_reason="stop",
            usage_total={},
        )

    asyncio.run(
        run_tools_skill(
            skill=skill,
            workspace="ws",
            user_prompt="answer",
            workspace_root=tmp_path,
            slice_fn=None,
            retrieve_fn=None,
            run_store=FakeRunStore(),
            mcp_registry=FakeMCPRegistry(),
            touch_invocation=lambda name: None,
            run_tool_loop_fn=fake_run_tool_loop,
            tool_context_cls=ToolContext,
            auto_emit_fn=lambda skill_arg, run_dir_arg: emitted.append((skill_arg.name, run_dir_arg)),
        )
    )

    assert emitted == [("future-skill", run_dir)]


def test_run_tools_skill_auto_emit_deliverables_reach_studio_route(tmp_path: Path) -> None:
    skill_dir = tmp_path / "future-skill"
    skill_dir.mkdir()
    skill = Skill(
        name="future-skill",
        path=str(skill_dir),
        skill_md_path=str(skill_dir / "SKILL.md"),
        frontmatter=SkillFrontmatter(
            name="future-skill",
            description="desc",
            metadata={"runtime": "tools"},
        ),
        body_md="body",
    )
    class FakeMCPRegistry:
        async def start_run_sessions(self, *, run_id, requested):
            return SimpleNamespace(sessions={}, started_names=[], warning_messages=lambda: [])

        async def shutdown_run(self, run_id):
            pass

    async def fake_run_tool_loop(**kwargs):
        return SimpleNamespace(
            response="# Finished Product\n\nThis is the final answer Studio should list.",
            warnings=[],
            turns=1,
            tool_calls=0,
            finish_reason="stop",
            usage_total={},
        )

    result = asyncio.run(
        run_tools_skill(
            skill=skill,
            workspace="ws",
            user_prompt="emit a product",
            workspace_root=tmp_path,
            slice_fn=None,
            retrieve_fn=None,
            run_store=SkillRunStore(),
            mcp_registry=FakeMCPRegistry(),
            touch_invocation=lambda name: None,
            run_tool_loop_fn=fake_run_tool_loop,
            tool_context_cls=ToolContext,
            auto_emit_fn=auto_emit_artifacts,
        )
    )

    app = FastAPI()
    register_skill_run_ui_routes(app, workspace_dir=lambda: tmp_path)
    response = TestClient(app).get("/api/ui/studio")

    assert response.status_code == 200
    rows = response.json()["deliverables"]
    by_filename = {row["filename"]: row for row in rows}
    assert set(by_filename) == {
        "future_skill_brief.docx",
    }
    assert all(row["run_id"] == result.run_id for row in rows)
    assert by_filename["future_skill_brief.docx"]["display_name"] == "Future Skill Brief"


def test_run_tools_skill_requires_workspace_root(tmp_path: Path) -> None:
    try:
        asyncio.run(
            run_tools_skill(
                skill=_skill(tmp_path),
                workspace="ws",
                user_prompt="answer",
                workspace_root=None,
                slice_fn=None,
                retrieve_fn=None,
                run_store=object(),
                mcp_registry=object(),
                touch_invocation=lambda name: None,
                run_tool_loop_fn=lambda **kwargs: None,
                tool_context_cls=ToolContext,
            )
        )
    except RuntimeError as exc:
        assert "workspace_root" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for missing workspace_root")