"""Neo4j-backed entity slices for tools-mode skills when VDB JSON lacks types."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from src.core.neo4j_config import get_neo4j_connection_config
from src.skills.context import SkillWorkspaceEvidenceStore


def _bucket_entities(
    rows: list[dict[str, Any]],
    *,
    limit_per_type: int,
) -> dict[str, list[dict[str, Any]]]:
    bucketed: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        entity_type = str(row.get("entity_type") or "unknown").lower()
        bucket = bucketed.setdefault(entity_type, [])
        if len(bucket) >= limit_per_type:
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        raw_src = str(row.get("source_id") or "")
        chunk_ids = [chunk.strip() for chunk in raw_src.split("<SEP>") if chunk.strip()]
        bucket.append(
            {
                "name": name,
                "description": (row.get("description") or "")[:400],
                "source_chunks": chunk_ids,
            }
        )
    return bucketed


async def neo4j_entity_slice(
    *,
    workspace_name: str,
    workspace_dir: Path,
    types: Optional[list[str]],
    limit_per_type: int,
    max_chunks_per_entity: int,
    max_relationships_per_entity: int,
    max_chunk_content_chars: int,
) -> Optional[dict[str, Any]]:
    """Return a briefing-book-shaped payload from Neo4j, or None if unavailable."""
    config = get_neo4j_connection_config(database_fallback=workspace_name)
    if not config.enabled:
        return None

    try:
        from neo4j import AsyncGraphDatabase
    except ImportError:  # pragma: no cover
        return None

    wanted = [str(value).strip().lower() for value in (types or []) if value]
    label = workspace_name.replace("`", "")
    driver = AsyncGraphDatabase.driver(config.uri, auth=config.auth)
    rows: list[dict[str, Any]] = []
    try:
        async with driver.session(database=config.database) as session:
            if wanted:
                result = await session.run(
                    f"""
                    UNWIND $types AS wanted_type
                    MATCH (n:`{label}`)
                    WHERE toLower(n.entity_type) = wanted_type
                    WITH wanted_type, n
                    ORDER BY coalesce(n.entity_name, n.entity_id, '')
                    WITH wanted_type, collect(n)[0..$limit] AS nodes
                    UNWIND nodes AS n
                    RETURN
                        wanted_type AS entity_type,
                        coalesce(n.entity_name, n.entity_id, '') AS name,
                        n.description AS description,
                        n.source_id AS source_id
                    """,
                    types=wanted,
                    limit=int(limit_per_type),
                )
            else:
                result = await session.run(
                    f"""
                    MATCH (n:`{label}`)
                    WHERE n.entity_type IS NOT NULL
                      AND NOT toLower(n.entity_type) IN ['concept', 'unknown']
                    WITH toLower(n.entity_type) AS entity_type, n
                    ORDER BY coalesce(n.entity_name, n.entity_id, '')
                    WITH entity_type, collect(n)[0..$limit] AS nodes
                    UNWIND nodes AS n
                    RETURN
                        entity_type,
                        coalesce(n.entity_name, n.entity_id, '') AS name,
                        n.description AS description,
                        n.source_id AS source_id
                    """,
                    limit=int(limit_per_type),
                )
            rows = [dict(record) async for record in result]
    except Exception:  # noqa: BLE001
        await driver.close()
        return None
    await driver.close()

    if not rows:
        return None

    bucketed = _bucket_entities(rows, limit_per_type=limit_per_type)
    if not bucketed:
        return None

    entity_chunk_map: dict[str, list[str]] = {}
    entity_name_set: set[str] = set()
    for entities in bucketed.values():
        for entity in entities:
            name = str(entity.get("name") or "").strip()
            if not name:
                continue
            entity_chunk_map[name] = list(entity.get("source_chunks") or [])
            entity_name_set.add(name.lower())

    store = SkillWorkspaceEvidenceStore(workspace_dir)
    return {
        "entities": bucketed,
        "source_chunks": store._load_source_chunks(  # noqa: SLF001
            entity_chunk_map,
            max_chunks_per_entity,
            max_chunk_content_chars=max_chunk_content_chars,
        ),
        "relationships": store._load_relationships(  # noqa: SLF001
            entity_name_set,
            max_relationships_per_entity,
        ),
        "slice_source": "neo4j",
    }