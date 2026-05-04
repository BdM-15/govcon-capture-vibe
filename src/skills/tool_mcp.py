"""MCP-backed ToolSpec adapters for the skill runtime."""

from __future__ import annotations

from typing import Any

from src.skills.tool_types import ToolContext, ToolError, ToolResult
from src.skills.tools import ToolSpec


def build_mcp_tool_specs(sessions: dict[str, Any]) -> list[ToolSpec]:
    """Wrap each MCP-discovered tool as a :class:`ToolSpec`."""
    specs: list[ToolSpec] = []
    for server_name, session in sessions.items():
        for descriptor in session.tools:
            specs.append(_build_one_mcp_spec(server_name, session, descriptor))
    return specs


def _build_one_mcp_spec(server_name: str, session: Any, descriptor: Any) -> ToolSpec:
    """Construct a single MCP-backed ToolSpec."""
    upstream_name = descriptor.name
    namespaced = descriptor.namespaced_name
    schema = descriptor.input_schema or {"type": "object", "properties": {}}
    description = descriptor.description or f"MCP tool {server_name}.{upstream_name}"

    async def _handler(ctx: ToolContext, **kwargs: Any) -> ToolResult:
        from src.skills.mcp_client import MCPError

        try:
            text = await session.call_tool(upstream_name, kwargs)
        except MCPError as exc:
            raise ToolError(str(exc)) from exc
        truncated = False
        if len(text) > ctx.max_read_bytes:
            text = text[: ctx.max_read_bytes]
            truncated = True
        return ToolResult(
            payload={
                "server": server_name,
                "tool": upstream_name,
                "truncated": truncated,
                "content": text,
            },
            truncated=truncated,
        )

    return ToolSpec(
        name=namespaced,
        description=description,
        parameters=schema,
        handler=_handler,
    )