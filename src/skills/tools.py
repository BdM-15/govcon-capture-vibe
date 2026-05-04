"""Tool registry for the skill runtime.

Skills run as multi-turn tool-calling agents. The runtime exposes six tools
to the model:

* ``read_file(path)`` — read a text file inside the skill folder
* ``run_script(path, stdin=None, timeout=60)`` — execute a script in the
  skill's ``scripts/`` folder under a sandboxed subprocess
* ``write_file(path, content)`` — persist an artifact to the run's
  ``artifacts/`` folder
* ``kg_query(cypher)`` — run a read-only Cypher query against the active
  workspace's Neo4j graph (no-op if Neo4j is not the active backend)
* ``kg_entities(types, limit, max_chunks_per_entity, max_relationships_per_entity)``
  — slice the workspace KG by entity type (Phase 1.5 bulk slice)
* ``kg_chunks(query, top_k, mode)`` — Phase 1.6 chat-grade hybrid retrieval

Every tool call is captured in the run transcript along with timing,
arguments, and a truncated preview of the result. Tools are designed to be
mechanical and bounded — model "thinking" stays in the assistant turns,
tools just fetch / execute / persist.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from src.skills.tool_filesystem import tool_read_file, tool_run_script, tool_write_file
from src.skills.tool_kg import tool_kg_chunks, tool_kg_entities, tool_kg_query
from src.skills.tool_types import ToolContext, ToolError, ToolResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Tool registry — used by the runtime to drive the model's tool_choice list
# ---------------------------------------------------------------------------


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[ToolResult]]

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def build_tool_specs() -> list[ToolSpec]:
    """Return the canonical six-tool registry.

    Order matters only for transcript readability; the model is free to call
    them in any order.
    """
    return [
        ToolSpec(
            name="read_file",
            description=(
                "Read a UTF-8 text file from the skill folder. Allowed roots: "
                "SKILL.md, references/, assets/, scripts/. Use this to load "
                "schemas, prompt templates, or example payloads bundled with "
                "the skill."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Skill-relative path, e.g. 'references/methodology.md'.",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=tool_read_file,
        ),
        ToolSpec(
            name="run_script",
            description=(
                "Execute a script (.py, .sh, .mjs, .js) under the skill's "
                "scripts/ folder OR any directory declared in this skill's "
                "metadata.script_paths frontmatter (typically a sibling "
                "utility skill like ../huashu-design/scripts for HTML\u2192PPTX/"
                "PDF rendering). Subprocess sandboxed: cwd locked to the "
                "owning skill, time-limited. Returns stdout, stderr, exit code."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Path relative to this skill's directory. Either "
                            "'scripts/<file>' for own scripts, or "
                            "'../<other_skill>/scripts/<file>' for a "
                            "cross-skill script declared in metadata.script_paths."
                        ),
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional CLI arguments appended after the script path, "
                            "e.g. ['--slides', '{artifacts}/slides', '--out', "
                            "'{artifacts}/deck.pdf']. Each entry must be a string; "
                            "capped at 32 entries. No shell expansion is performed. "
                            "Placeholders {run_dir}, {artifacts}, {skill_dir} are "
                            "substituted with absolute paths so you can reference "
                            "the run's artifacts/ folder without knowing the layout."
                        ),
                        "maxItems": 32,
                    },
                    "stdin": {
                        "type": "string",
                        "description": "Optional stdin to pipe to the script.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Max seconds before SIGKILL. Capped by the runtime.",
                        "minimum": 1,
                        "maximum": 60,
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=tool_run_script,
        ),
        ToolSpec(
            name="write_file",
            description=(
                "Persist a UTF-8 text artifact to <run_dir>/artifacts/. Use "
                "this for proposal drafts, compliance matrices, infographic "
                "HTML, or any deliverable the user should download. Path is "
                "relative to the artifacts/ root."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Artifact path relative to artifacts/, e.g. 'volume-1-outline.md'.",
                    },
                    "content": {"type": "string", "description": "File body."},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            handler=tool_write_file,
        ),
        ToolSpec(
            name="kg_query",
            description=(
                "Run a read-only Cypher query against the active workspace's "
                "Neo4j graph. Mutating clauses (CREATE/MERGE/DELETE/SET) are "
                "rejected. Returns up to 100 rows. If the workspace uses "
                "NetworkXStorage instead of Neo4j, the call returns "
                "available=false and the model should use kg_entities or "
                "kg_chunks instead."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "cypher": {
                        "type": "string",
                        "description": "Read-only Cypher query (MATCH/RETURN style).",
                    },
                },
                "required": ["cypher"],
                "additionalProperties": False,
            },
            handler=tool_kg_query,
        ),
        ToolSpec(
            name="kg_entities",
            description=(
                "Slice the active workspace's knowledge graph by entity type. "
                "Returns a deterministic bucket of entities with their "
                "descriptions, source chunk IDs, and connecting relationships. "
                "Use when you know which entity types you need (e.g. "
                "['proposal_instruction', 'evaluation_factor'])."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entity types to include. Omit to get all non-noise types.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entities per type (capped by runtime).",
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "max_chunks_per_entity": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 5,
                        "description": "Per-entity cap on returned source chunk IDs.",
                    },
                    "max_relationships_per_entity": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 20,
                        "description": "Per-entity cap on returned KG relationships.",
                    },
                },
                "additionalProperties": False,
            },
            handler=tool_kg_entities,
        ),
        ToolSpec(
            name="kg_chunks",
            description=(
                "Run chat-grade hybrid retrieval (Phase 1.6) over the active "
                "workspace. Returns ranked entity names + chunk IDs scored "
                "against the query. Use when you don't know which entity "
                "types to ask for, or when answering a free-text user question."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language retrieval query.",
                    },
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 30,
                        "description": "Number of entity hits to return.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["hybrid", "local", "global", "naive", "mix"],
                        "description": "Retrieval mode (default 'hybrid').",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=tool_kg_chunks,
        ),
    ]


def serialize_tool_payload_for_model(result: ToolResult, *, char_cap: int = 12_000) -> str:
    """Serialize a tool result into the JSON string fed back to the model.

    OpenAI's chat protocol expects the ``content`` of a ``role: tool`` message
    to be a string; we use compact JSON. Long payloads are truncated with a
    sentinel so the model knows it's incomplete.
    """
    try:
        text = json.dumps(result.payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        text = json.dumps({"error": f"unable to serialize payload: {exc}"})
    if len(text) > char_cap:
        text = text[:char_cap] + f'\n…[truncated at {char_cap} chars]'
    return text


# ---------------------------------------------------------------------------
# MCP tool adapter (Phase 4a)
# ---------------------------------------------------------------------------


def build_mcp_tool_specs(sessions: dict[str, Any]) -> list[ToolSpec]:
    """Wrap each MCP-discovered tool as a :class:`ToolSpec`.

    Tool names are namespaced as ``mcp__<server>__<tool>`` so the LLM can
    distinguish them from the in-process tools. The handler ignores its
    ``ctx`` argument (MCP sessions are closed over from the dict passed in
    at registration time) but still accepts it so it slots into the same
    dispatch loop as the core tools.

    Args:
        sessions: ``{server_alias: MCPSession}`` produced by
            :meth:`MCPRegistry.start_run_sessions` for the active run.
    """
    specs: list[ToolSpec] = []
    for server_name, session in sessions.items():
        for descriptor in session.tools:
            specs.append(_build_one_mcp_spec(server_name, session, descriptor))
    return specs


def _build_one_mcp_spec(server_name: str, session: Any, descriptor: Any) -> ToolSpec:
    """Construct a single MCP-backed ToolSpec.

    Closes over ``session`` + ``descriptor`` so the handler can dispatch the
    actual ``call_tool`` without a global lookup. Errors raised by the
    session are translated into :class:`ToolError` so the runtime's
    standard error-envelope path takes over.
    """
    upstream_name = descriptor.name
    namespaced = descriptor.namespaced_name
    schema = descriptor.input_schema or {"type": "object", "properties": {}}
    description = descriptor.description or f"MCP tool {server_name}.{upstream_name}"

    async def _handler(ctx: ToolContext, **kwargs: Any) -> ToolResult:
        # Late import to avoid circulars (mcp_client imports nothing from here
        # but tools.py is imported by the runtime which also imports mcp_client).
        from src.skills.mcp_client import MCPError

        try:
            text = await session.call_tool(upstream_name, kwargs)
        except MCPError as exc:
            raise ToolError(str(exc)) from exc
        # MCP results are already strings; surface as-is to the model. Truncate
        # to honour the read-byte cap so a runaway server can't blow context.
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

