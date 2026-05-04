"""Knowledge-graph-backed tool handlers for the skill runtime."""

from __future__ import annotations

import re
from typing import Any, Optional

from src.core.neo4j_config import get_neo4j_connection_config
from src.skills.tool_types import ToolContext, ToolError, ToolResult

_KG_QUERY_ALLOWED_PREFIX = re.compile(r"^\s*(MATCH|OPTIONAL MATCH|WITH|UNWIND|CALL|RETURN)\b", re.I)
_KG_QUERY_DENY = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV)\b",
    re.I,
)


async def tool_kg_query(ctx: ToolContext, cypher: str) -> ToolResult:
    if not isinstance(cypher, str) or not cypher.strip():
        raise ToolError("cypher must be a non-empty string")
    if _KG_QUERY_DENY.search(cypher):
        raise ToolError("kg_query is read-only; mutating clauses are not allowed")
    if not _KG_QUERY_ALLOWED_PREFIX.match(cypher):
        raise ToolError("cypher must start with MATCH/OPTIONAL MATCH/WITH/UNWIND/CALL/RETURN")

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
        from neo4j import AsyncGraphDatabase
    except ImportError as exc:  # pragma: no cover
        raise ToolError("neo4j driver not installed") from exc

    driver = AsyncGraphDatabase.driver(config.uri, auth=config.auth)
    rows: list[dict[str, Any]] = []
    try:
        async with driver.session(database=config.database) as session:
            result = await session.run(cypher)
            async for record in result:
                rows.append({key: jsonable(value) for key, value in record.items()})
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


def jsonable(value: Any) -> Any:
    items = getattr(value, "items", None)
    if callable(items):
        try:
            return {key: jsonable(item) for key, item in items()}
        except Exception:  # noqa: BLE001
            pass
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
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
    if ctx.slice_fn is None:
        raise ToolError("kg_entities is unavailable (no slice_fn wired)")
    safe_limit = max(1, min(int(limit or 25), ctx.max_kg_entities_per_type))
    safe_chunks = max(0, min(int(max_chunks_per_entity or 0), 5))
    safe_rels = max(0, min(int(max_relationships_per_entity or 0), 20))
    types_list: Optional[list[str]] = None
    if types:
        if not isinstance(types, list):
            raise ToolError("types must be a list of strings")
        types_list = [str(value) for value in types if value]
    data = ctx.slice_fn(types_list, safe_limit, safe_chunks, safe_rels, None)
    return ToolResult(payload=data)


async def tool_kg_chunks(
    ctx: ToolContext,
    query: str,
    top_k: int = 15,
    mode: str = "hybrid",
) -> ToolResult:
    if ctx.retrieve_fn is None:
        raise ToolError("kg_chunks is unavailable (no retrieve_fn wired)")
    if not isinstance(query, str) or not query.strip():
        raise ToolError("query must be a non-empty string")
    safe_top_k = max(1, min(int(top_k or 15), ctx.max_kg_chunks))
    valid_modes = {"hybrid", "local", "global", "naive", "mix"}
    safe_mode = mode if mode in valid_modes else "hybrid"
    payload = await ctx.retrieve_fn(query, "", safe_mode, safe_top_k)
    return ToolResult(
        payload={
            "matched_entity_names": sorted(payload.get("names") or []),
            "matched_chunk_ids": sorted(payload.get("chunk_ids") or []),
            "metadata": payload.get("metadata") or {},
        }
    )