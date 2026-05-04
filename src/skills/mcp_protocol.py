"""Pure MCP protocol helpers used by the session transport."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


_TOOL_NAME_MAX = 64


@dataclass
class MCPToolDescriptor:
    """An MCP-discovered tool, ready to be wrapped into a ToolSpec."""

    server: str
    name: str
    description: str
    input_schema: dict[str, Any]

    @property
    def namespaced_name(self) -> str:
        candidate = f"mcp__{self.server}__{self.name}"
        if len(candidate) > _TOOL_NAME_MAX:
            candidate = candidate[:_TOOL_NAME_MAX]
        return candidate


def parse_tool_descriptors(
    server_name: str,
    raw_tools: list[Any],
) -> list[MCPToolDescriptor]:
    """Normalize ``tools/list`` payload entries into descriptors."""
    descriptors: list[MCPToolDescriptor] = []
    for entry in raw_tools:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        schema = entry.get("inputSchema") or {"type": "object", "properties": {}}
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}}
        descriptors.append(
            MCPToolDescriptor(
                server=server_name,
                name=name,
                description=str(entry.get("description") or "").strip(),
                input_schema=schema,
            )
        )
    return descriptors


def extract_text_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return json.dumps(content, ensure_ascii=False, default=str)
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        kind = item.get("type")
        if kind == "text":
            parts.append(str(item.get("text") or ""))
        elif kind == "image":
            parts.append(f"[image:{item.get('mimeType') or 'unknown'}]")
        elif kind == "resource":
            resource = item.get("resource")
            uri = resource.get("uri") if isinstance(resource, dict) else None
            parts.append(f"[resource:{uri or 'embedded'}]")
        else:
            parts.append(json.dumps(item, ensure_ascii=False, default=str))
    return "\n".join(part for part in parts if part)