import asyncio
from pathlib import Path
from types import SimpleNamespace

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

    assert roots == [Path(skill.path) / "shared-scripts"]
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
            response="done",
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

    assert result.response == "done"
    assert result.run_id == "run-1"
    assert touched == ["demo-skill"]
    assert emitted == [("demo-skill", run_dir)]
    assert captured["start_run_sessions"] == {"run_id": "run-1", "requested": ["demo-mcp"]}
    assert captured["persist_tools_run"]["warnings"][0] == "script_paths: skipping non-string entry 7"
    assert "startup warning" in captured["persist_tools_run"]["warnings"]
    assert "loop warning" in captured["persist_tools_run"]["warnings"]


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