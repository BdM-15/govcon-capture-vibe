import asyncio
import json
from pathlib import Path

import pytest

from src.skills.tool_registry import tool_invoke_skill
from src.skills.tools import ToolContext, ToolError, tool_read_file, tool_run_script, tool_write_file


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