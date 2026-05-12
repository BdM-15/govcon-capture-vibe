import asyncio
import json

from src.skills.llm_chat import ChatToolCall
from src.skills.runtime import (
    compose_system_prompt,
    dispatch_tool_call,
    persist_transcript,
)
from src.skills.tool_registry import ToolSpec
from src.skills.tool_types import ToolContext, ToolError, ToolResult


def _ctx(tmp_path) -> ToolContext:
    return ToolContext(
        skill_name="test",
        skill_dir=tmp_path,
        run_dir=tmp_path,
        workspace_dir=tmp_path,
        workspace_name="demo",
    )


def test_compose_system_prompt_includes_contract_bits() -> None:
    prompt = compose_system_prompt(
        skill_name="demo-skill",
        skill_body="1. Do work",
        workspace_name="ws-a",
        tool_names=["kg_query", "write_file"],
    )

    assert "demo-skill" in prompt
    assert "ws-a" in prompt
    assert "1. Do work" in prompt
    assert "kg_query, write_file" in prompt
    assert "do not retry the same call unchanged" in prompt


def test_persist_transcript_writes_json(tmp_path) -> None:
    transcript = [{"kind": "assistant", "content": "ok"}]

    persist_transcript(tmp_path, transcript)

    saved = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))
    assert saved == transcript


def test_dispatch_tool_call_success_and_transcript_extra(tmp_path) -> None:
    async def handler(ctx, value: str) -> ToolResult:
        return ToolResult(payload={"value": value}, transcript_extra={"file": "x"})

    spec = ToolSpec(
        name="demo",
        description="desc",
        parameters={"type": "object"},
        handler=handler,
    )

    payload, extra = asyncio.run(
        dispatch_tool_call(
            ChatToolCall(id="1", name="demo", arguments_json='{"value": "ok"}'),
            {"demo": spec},
            _ctx(tmp_path),
        )
    )

    assert json.loads(payload) == {"value": "ok"}
    assert extra == {"truncated": False, "file": "x"}


def test_dispatch_tool_call_returns_structured_errors(tmp_path) -> None:
    async def handler(ctx, value: str) -> ToolResult:
        raise ToolError(f"bad {value}")

    spec = ToolSpec(
        name="demo",
        description="desc",
        parameters={"type": "object"},
        handler=handler,
    )

    payload, extra = asyncio.run(
        dispatch_tool_call(
            ChatToolCall(id="1", name="demo", arguments_json='{"value": "oops"}'),
            {"demo": spec},
            _ctx(tmp_path),
        )
    )

    assert json.loads(payload) == {"error": "bad oops"}
    assert extra == {"error": "bad oops"}


def test_dispatch_tool_call_rejects_bad_json_and_unknown_tool(tmp_path) -> None:
    async def handler(ctx, value: str) -> ToolResult:
        return ToolResult(payload={"value": value})

    spec = ToolSpec(
        name="demo",
        description="desc",
        parameters={"type": "object"},
        handler=handler,
    )

    bad_payload, bad_extra = asyncio.run(
        dispatch_tool_call(
            ChatToolCall(id="1", name="demo", arguments_json='[1,2,3]'),
            {"demo": spec},
            _ctx(tmp_path),
        )
    )
    unknown_payload, unknown_extra = asyncio.run(
        dispatch_tool_call(
            ChatToolCall(id="2", name="missing", arguments_json='{}'),
            {},
            _ctx(tmp_path),
        )
    )

    assert "invalid arguments JSON" in json.loads(bad_payload)["error"]
    assert "invalid arguments JSON" in bad_extra["error"]
    assert json.loads(unknown_payload) == {"error": "unknown tool 'missing'"}
    assert unknown_extra == {"error": "unknown tool 'missing'"}