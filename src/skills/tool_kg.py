"""Knowledge-graph-backed tool handlers for the skill runtime."""

from __future__ import annotations

import re
from typing import Any, Optional

from src.core.neo4j_config import get_neo4j_connection_config
from src.skills.context import SkillWorkspaceEvidenceStore
from src.skills.tool_kg_neo4j import neo4j_entity_slice
from src.skills.tool_types import ToolContext, ToolError, ToolResult

_KG_QUERY_ALLOWED_PREFIX = re.compile(r"^\s*(MATCH|OPTIONAL MATCH|WITH|UNWIND|CALL|RETURN)\b", re.I)
_KG_QUERY_DENY = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV)\b",
    re.I,
)


def _slice_is_empty(payload: dict[str, Any]) -> bool:
    entities = payload.get("entities")
    if not isinstance(entities, dict):
        return False
    if not entities:
        return True
    return not any(isinstance(bucket, list) and bucket for bucket in entities.values())


def _chunks_from_aquery_data(
    ranked_chunks: list[Any],
    ctx: ToolContext,
    chunk_ids: set[str],
) -> list[dict[str, Any]]:
    """Prefer verbatim chunk bodies from aquery_data before VDB reload."""
    cap = max(500, int(getattr(ctx, "max_chunk_content_chars", 8000) or 8000))
    source_chunks: list[dict[str, Any]] = []
    for chunk in ranked_chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_id = str(chunk.get("chunk_id") or chunk.get("__id__") or "").strip()
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        if chunk_ids and chunk_id and chunk_id not in chunk_ids:
            continue
        truncated = len(content) > cap
        source_chunks.append(
            {
                "chunk_id": chunk_id,
                "file_path": chunk.get("file_path"),
                "content": content[:cap],
                "truncated": truncated,
            }
        )
    return source_chunks


def _load_retrieved_chunks(
    ctx: ToolContext,
    chunk_ids: set[str],
) -> list[dict[str, Any]]:
    if not chunk_ids:
        return []
    cap = max(500, int(getattr(ctx, "max_chunk_content_chars", 8000) or 8000))
    store = SkillWorkspaceEvidenceStore(ctx.workspace_dir)
    return store._load_source_chunks(  # noqa: SLF001
        {},
        max_chunks_per_entity=0,
        retrieval_chunk_ids=chunk_ids,
        max_chunk_content_chars=cap,
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
    max_chunks_per_entity: int = 0,
    max_relationships_per_entity: int = 0,
) -> ToolResult:
    if getattr(ctx, "research_harness_config", None) is not None:
        from src.skills.research_harness import get_phase
        from src.skills.research_plan import check_kg_entities_plan

        blocked = check_kg_entities_plan(ctx.run_dir, phase=get_phase(ctx.run_dir))
        if blocked is not None:
            return blocked
    if ctx.slice_fn is None:
        raise ToolError("kg_entities is unavailable (no slice_fn wired)")
    safe_limit = max(1, min(int(limit or 25), ctx.max_kg_entities_per_type))
    requested_chunks = int(max_chunks_per_entity or 0)
    if requested_chunks <= 0:
        requested_chunks = max(8, min(ctx.max_kg_chunks_per_entity, 15))
    safe_chunks = max(0, min(requested_chunks, ctx.max_kg_chunks_per_entity))
    requested_rels = int(max_relationships_per_entity or 0)
    if requested_rels <= 0:
        requested_rels = max(8, min(ctx.max_kg_relationships_per_entity, 15))
    safe_rels = max(0, min(requested_rels, ctx.max_kg_relationships_per_entity))
    types_list: Optional[list[str]] = None
    if types:
        if not isinstance(types, list):
            raise ToolError("types must be a list of strings")
        types_list = [str(value) for value in types if value]

    data = ctx.slice_fn(types_list, safe_limit, safe_chunks, safe_rels, None)
    if _slice_is_empty(data):
        fallback = await neo4j_entity_slice(
            workspace_name=ctx.workspace_name,
            workspace_dir=ctx.workspace_dir,
            types=types_list,
            limit_per_type=safe_limit,
            max_chunks_per_entity=safe_chunks,
            max_relationships_per_entity=safe_rels,
            max_chunk_content_chars=int(getattr(ctx, "max_chunk_content_chars", 8000) or 8000),
        )
        if isinstance(fallback, dict):
            data = fallback
        elif types_list:
            data = {
                **data,
                "warning": (
                    "typed kg_entities slice returned 0 entities from workspace VDB; "
                    "Neo4j fallback unavailable or also empty"
                ),
            }
    entity_counts: dict[str, int] = {}
    entities = data.get("entities")
    if isinstance(entities, dict):
        for key, bucket in entities.items():
            if isinstance(bucket, list):
                entity_counts[str(key)] = len(bucket)
    return ToolResult(
        payload=data,
        transcript_extra={"entity_counts_by_type": entity_counts},
    )


async def tool_kg_chunks(
    ctx: ToolContext,
    query: str,
    top_k: int = 15,
    mode: str = "hybrid",
) -> ToolResult:
    if not isinstance(query, str) or not query.strip():
        raise ToolError("query must be a non-empty string")
    if getattr(ctx, "research_harness_config", None) is not None:
        from src.skills.research_harness import get_phase
        from src.skills.research_plan import check_kg_chunks_plan

        blocked = check_kg_chunks_plan(ctx.run_dir, query=query, phase=get_phase(ctx.run_dir))
        if blocked is not None:
            from src.skills.research_harness import load_harness_state, save_harness_state
            from src.skills.research_plan import append_prior_query

            state = load_harness_state(ctx.run_dir)
            if state:
                append_prior_query(state, query)
                save_harness_state(ctx.run_dir, state)
            return blocked
    if ctx.retrieve_fn is None:
        raise ToolError("kg_chunks is unavailable (no retrieve_fn wired)")
    safe_top_k = max(1, min(int(top_k or 15), ctx.max_kg_chunks))
    valid_modes = {"hybrid", "local", "global", "naive", "mix"}
    safe_mode = mode if mode in valid_modes else "hybrid"
    payload = await ctx.retrieve_fn(query, "", safe_mode, safe_top_k)
    chunk_ids = {str(chunk_id) for chunk_id in (payload.get("chunk_ids") or set()) if chunk_id}
    ranked_chunks = payload.get("chunks") or []
    source_chunks = _chunks_from_aquery_data(ranked_chunks, ctx, chunk_ids)
    if not source_chunks:
        source_chunks = _load_retrieved_chunks(ctx, chunk_ids)
    grounded_entities = payload.get("entities") or []
    grounded_relationships = payload.get("relationships") or []
    metadata = dict(payload.get("metadata") or {})
    transcript_extra: dict[str, Any] = {
        "chunk_count": len(chunk_ids),
        "entity_count": len(grounded_entities),
        "relationship_count": len(grounded_relationships),
    }
    try:
        from src.extraction.govcon_reranker import pop_last_rerank_stats

        rerank_stats = pop_last_rerank_stats()
        if rerank_stats:
            metadata["rerank"] = rerank_stats
            transcript_extra["rerank"] = rerank_stats
    except ImportError:
        pass
    return ToolResult(
        payload={
            "matched_entity_names": sorted(payload.get("names") or []),
            "matched_chunk_ids": sorted(chunk_ids),
            "grounded_entities": grounded_entities,
            "grounded_relationships": grounded_relationships,
            "references": payload.get("references") or [],
            "source_chunks": source_chunks,
            "metadata": metadata,
        },
        transcript_extra=transcript_extra,
    )