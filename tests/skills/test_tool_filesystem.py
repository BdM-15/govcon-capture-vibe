import asyncio
import json
from pathlib import Path

import pytest

from src.skills.tool_registry import build_tool_specs
from src.skills.tool_skill_chain import tool_invoke_skill
from src.skills.tools import (
    ToolContext,
    ToolError,
    tool_promote_global_note,
    tool_read_file,
    tool_read_global_note,
    tool_run_script,
    tool_write_file,
    tool_write_global_note,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _ctx(tmp_path: Path) -> ToolContext:
    skill_dir = tmp_path / "skill"
    run_dir = tmp_path / "run"
    skill_dir.mkdir()
    run_dir.mkdir()
    return ToolContext(
        skill_name="test",
        skill_dir=skill_dir,
        run_dir=run_dir,
        workspace_dir=tmp_path,
        workspace_name="demo",
    )


def _repo_ctx(tmp_path: Path) -> ToolContext:
    repo_root = tmp_path / "repo"
    workspace_dir = repo_root / "rag_storage" / "demo"
    skill_dir = tmp_path / "skill"
    run_dir = tmp_path / "run"
    workspace_dir.mkdir(parents=True)
    skill_dir.mkdir()
    run_dir.mkdir()
    return ToolContext(
        skill_name="phase-promoter",
        skill_dir=skill_dir,
        run_dir=run_dir,
        workspace_dir=workspace_dir,
        workspace_name="demo",
    )


def test_tool_read_file_reads_allowed_reference_and_truncates(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ref = ctx.skill_dir / "references"
    ref.mkdir()
    (ref / "note.md").write_text("abcdef", encoding="utf-8")
    ctx.max_read_bytes = 4

    result = _run(tool_read_file(ctx, "references/note.md"))

    assert result.payload["path"] == "references/note.md"
    assert result.payload["content"] == "abcd"
    assert result.payload["truncated"] is True


def test_tool_read_file_rejects_non_allowlisted_path(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.skill_dir / "other.txt").write_text("x", encoding="utf-8")

    with pytest.raises(ToolError, match="restricted"):
        _run(tool_read_file(ctx, "other.txt"))


def test_tool_write_file_strips_artifacts_prefix(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)

    result = _run(tool_write_file(ctx, "artifacts/out.md", "hello"))

    assert result.payload == {"path": "artifacts/out.md", "bytes_written": 5}
    assert (ctx.run_dir / "artifacts" / "out.md").read_text(encoding="utf-8") == "hello"


def test_tool_write_file_persists_display_name_manifest(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)

    result = _run(
        tool_write_file(
            ctx,
            "brief.md",
            "hello",
            label="AFCAP V Vehicle Burn Brief",
        )
    )

    manifest = json.loads((ctx.run_dir / "artifacts_manifest.json").read_text(encoding="utf-8"))
    assert result.payload["display_name"] == "AFCAP V Vehicle Burn Brief"
    assert manifest == {
        "brief.md": {"display_name": "AFCAP V Vehicle Burn Brief"}
    }


def test_tool_run_script_executes_python_script(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    scripts = ctx.skill_dir / "scripts"
    scripts.mkdir()
    script = scripts / "echo.py"
    script.write_text("print('ok from script')\n", encoding="utf-8")

    result = _run(tool_run_script(ctx, "scripts/echo.py"))

    assert result.payload["script"] == "scripts/echo.py"
    assert result.payload["exit_code"] == 0
    assert "ok from script" in result.payload["stdout"]
    assert Path(result.transcript_extra["stdout_file"]).is_file()


def test_tool_invoke_skill_delegates_to_configured_handler(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    captured = {}

    async def invoke_skill_fn(name, prompt, context):
        captured.update({"name": name, "prompt": prompt, "context": context})
        from src.skills.tool_types import ToolResult

        return ToolResult(payload={"skill": name, "run_id": "run-1"})

    ctx.invoke_skill_fn = invoke_skill_fn

    result = _run(tool_invoke_skill(ctx, "child", "do work", {"x": 1}))

    assert result.payload == {"skill": "child", "run_id": "run-1"}
    assert captured == {"name": "child", "prompt": "do work", "context": {"x": 1}}


def test_tool_invoke_skill_rejects_recursive_self_call(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ctx.invoke_skill_fn = lambda *args: None

    with pytest.raises(ToolError, match="current skill"):
        _run(tool_invoke_skill(ctx, "test", "do work"))


def test_phase_promoter_tool_specs_include_global_write_tools() -> None:
    names = [spec.name for spec in build_tool_specs(skill_name="phase-promoter")]

    assert "read_global_note" in names
    assert "write_global_note" in names
    assert "promote_global_note" in names
    assert "write_global_note" not in [spec.name for spec in build_tool_specs(skill_name="price-to-win")]


def test_global_idea_capturer_tool_specs_include_direct_global_write() -> None:
    names = [spec.name for spec in build_tool_specs(skill_name="global-idea-capturer")]

    assert "write_global_note" in names
    assert "promote_global_note" not in names


def test_tool_write_and_read_global_note_round_trip(tmp_path: Path) -> None:
    ctx = _repo_ctx(tmp_path)
    content = "---\nstatus: evergreen\ntags: [meta]\n---\n\nKnowledge note\n"

    write_result = _run(tool_write_global_note(ctx, "notes/topic.md", content))
    read_result = _run(tool_read_global_note(ctx, "global/notes/topic.md"))

    target = tmp_path / "repo" / "global" / "notes" / "topic.md"
    assert write_result.payload["path"] == "notes/topic.md"
    assert write_result.payload["absolute_path"] == str(target)
    assert target.read_text(encoding="utf-8") == content
    assert read_result.payload["path"] == "notes/topic.md"
    assert read_result.payload["content"] == content
    assert read_result.payload["frontmatter"]["status"] == "evergreen"


def test_tool_promote_global_note_copies_into_workspace_sources(tmp_path: Path) -> None:
    ctx = _repo_ctx(tmp_path)
    content = "---\nstatus: evergreen\ntags: [meta]\n---\n\nPromote me\n"
    _run(tool_write_global_note(ctx, "notes/promote-me.md", content))

    result = _run(tool_promote_global_note(ctx, "notes/promote-me.md"))

    target = tmp_path / "repo" / "rag_storage" / "demo" / "sources" / "promote-me.md"
    assert result.payload == {
        "source": "notes/promote-me.md",
        "workspace": "demo",
        "target": str(target),
    }
    assert target.read_text(encoding="utf-8") == content