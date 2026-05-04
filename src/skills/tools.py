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
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from src.core.neo4j_config import get_neo4j_connection_config
from src.skills.tool_filesystem import tool_read_file, tool_run_script, tool_write_file
from src.skills.tool_types import ToolContext, ToolError, ToolResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------


# Allowlist for kg_query: only true read-only Cypher. Anything else is rejected.
_KG_QUERY_ALLOWED_PREFIX = re.compile(r"^\s*(MATCH|OPTIONAL MATCH|WITH|UNWIND|CALL|RETURN)\b", re.I)
_KG_QUERY_DENY = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV)\b",
    re.I,
)


async def tool_kg_query(ctx: ToolContext, cypher: str) -> ToolResult:
    """Run a read-only Cypher query against the active workspace's Neo4j DB.

    Returns up to 100 rows. Mutating clauses are rejected. If the active
    backend is NetworkX (no Neo4j configured), returns a structured error
    so the model can fall back to ``kg_query`` alternatives.
    """
    if not isinstance(cypher, str) or not cypher.strip():
        raise ToolError("cypher must be a non-empty string")
    if _KG_QUERY_DENY.search(cypher):
        raise ToolError("kg_query is read-only; mutating clauses are not allowed")
    if not _KG_QUERY_ALLOWED_PREFIX.match(cypher):
        raise ToolError(
            "cypher must start with MATCH/OPTIONAL MATCH/WITH/UNWIND/CALL/RETURN"
        )

    config = get_neo4j_connection_config(database_fallback=ctx.workspace_name)
    if not config.enabled:
        return ToolResult(
            payload={
                "available": False,
                "reason": (
                    f"GRAPH_STORAGE={config.graph_storage or 'NetworkXStorage'}; "
                    "kg_query requires Neo4JStorage. Use kg_entities or kg_chunks instead."
                ),
                "rows": [],
            }
        )

    try:
        from neo4j import AsyncGraphDatabase  # local import — optional dep
    except ImportError as exc:  # pragma: no cover
        raise ToolError("neo4j driver not installed") from exc

    driver = AsyncGraphDatabase.driver(config.uri, auth=config.auth)
    rows: list[dict[str, Any]] = []
    try:
        async with driver.session(database=config.database) as session:
            result = await session.run(cypher)
            async for record in result:
                rows.append({k: _jsonable(v) for k, v in record.items()})
                if len(rows) >= 100:
                    break
    except Exception as exc:  # noqa: BLE001
        await driver.close()
        raise ToolError(f"kg_query failed: {exc}") from exc
    await driver.close()

    return ToolResult(
        payload={
            "available": True,
            "row_count": len(rows),
            "truncated": len(rows) >= 100,
            "rows": rows,
        },
        truncated=len(rows) >= 100,
    )


def _jsonable(value: Any) -> Any:
    """Best-effort conversion of Neo4j record values to JSON-serializable shapes."""
    # Neo4j Node / Relationship expose dict-like .items()
    items = getattr(value, "items", None)
    if callable(items):
        try:
            return {k: _jsonable(v) for k, v in items()}
        except Exception:  # noqa: BLE001
            pass
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


async def tool_kg_entities(
    ctx: ToolContext,
    types: Optional[list[str]] = None,
    limit: int = 25,
    max_chunks_per_entity: int = 2,
    max_relationships_per_entity: int = 5,
) -> ToolResult:
    """Slice the workspace KG by entity type.

    Reuses the route layer's Phase 1.5 bulk slice (``_slice_workspace_entities``).
    """
    if ctx.slice_fn is None:
        raise ToolError("kg_entities is unavailable (no slice_fn wired)")
    safe_limit = max(1, min(int(limit or 25), ctx.max_kg_entities_per_type))
    safe_chunks = max(0, min(int(max_chunks_per_entity or 0), 5))
    safe_rels = max(0, min(int(max_relationships_per_entity or 0), 20))
    types_list: Optional[list[str]] = None
    if types:
        if not isinstance(types, list):
            raise ToolError("types must be a list of strings")
        types_list = [str(t) for t in types if t]
    data = ctx.slice_fn(types_list, safe_limit, safe_chunks, safe_rels, None)
    return ToolResult(payload=data)


async def tool_kg_chunks(
    ctx: ToolContext,
    query: str,
    top_k: int = 15,
    mode: str = "hybrid",
) -> ToolResult:
    """Run chat-grade hybrid retrieval and return ranked entities + chunks.

    Reuses the route layer's Phase 1.6 helper (``_retrieve_relevant_entities_for_skill``).
    The model can then call ``kg_entities`` with a filter or just consume the
    retrieval payload directly.
    """
    if ctx.retrieve_fn is None:
        raise ToolError("kg_chunks is unavailable (no retrieve_fn wired)")
    if not isinstance(query, str) or not query.strip():
        raise ToolError("query must be a non-empty string")
    safe_top_k = max(1, min(int(top_k or 15), ctx.max_kg_chunks))
    valid_modes = {"hybrid", "local", "global", "naive", "mix"}
    safe_mode = mode if mode in valid_modes else "hybrid"
    payload = await ctx.retrieve_fn(query, "", safe_mode, safe_top_k)
    # `payload` is {names: set, chunk_ids: set, metadata: dict} — sets aren't
    # JSON-safe, so coerce.
    return ToolResult(
        payload={
            "matched_entity_names": sorted(payload.get("names") or []),
            "matched_chunk_ids": sorted(payload.get("chunk_ids") or []),
            "metadata": payload.get("metadata") or {},
        }
    )


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

