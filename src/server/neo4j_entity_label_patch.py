"""Monkey-patch to restore entity-type Neo4j labels dropped by LightRAG rc3.

LightRAG 1.4.13 wrote entity_type as a Neo4j label on every node:

    MERGE (n:`{workspace}` {entity_id: $id})
    SET n += $props
    SET n:`{entity_type}`          ← made types browsable in Neo4j Browser

LightRAG rc3 (current pin) dropped that SET line. Entity type is still stored
as the n.entity_type property, but the ontology type no longer appears as a
Neo4j label — so Neo4j Browser only shows the workspace label, not the 32-type
breakdown.

``install_neo4j_entity_label_patch()`` restores the original behavior by
monkey-patching ``Neo4JStorage.upsert_node`` and
``Neo4JStorage.upsert_nodes_batch``.

``backfill_entity_type_labels(driver, database, workspace)`` backfills labels
for nodes already in the graph (needed for workspaces ingested before the
patch).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo4j import AsyncDriver  # noqa: F401

logger = logging.getLogger(__name__)

_PATCH_APPLIED = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_label(raw: str) -> str:
    """Return a Neo4j-safe label string.

    - Strips backticks (they'd break the f-string label embedding).
    - Takes only the first value if the string is comma-separated.
    - Falls back to 'UNKNOWN' for empty input.
    """
    label = str(raw).replace("`", "").strip()
    if "," in label:
        label = label.split(",")[0].strip()
    return label or "UNKNOWN"


# ---------------------------------------------------------------------------
# Patched methods
# ---------------------------------------------------------------------------


async def _patched_upsert_node(
    self,
    node_id: str,
    node_data: dict[str, str],
) -> None:
    """Drop-in replacement that adds ``SET n:`{entity_type}``` after SET n."""
    from neo4j import AsyncManagedTransaction  # local import — already in venv

    workspace_label = self._get_workspace_label()
    properties = node_data
    if "entity_id" not in properties:
        raise ValueError("Neo4j: node properties must contain an 'entity_id' field")

    raw_type = str(properties.get("entity_type") or "UNKNOWN")
    if raw_type != (sanitized := _sanitize_label(raw_type)):
        logger.warning(
            "[%s] entity_type sanitized in upsert_node: '%s' -> '%s'",
            self.workspace,
            raw_type,
            sanitized,
        )
        properties = dict(properties)
        properties["entity_type"] = sanitized

    entity_type = sanitized

    try:
        async with self._driver.session(database=self._DATABASE) as session:

            async def execute_upsert(tx: AsyncManagedTransaction) -> None:
                query = (
                    f"MERGE (n:`{workspace_label}` {{entity_id: $entity_id}})\n"
                    f"SET n += $properties\n"
                    f"SET n:`{entity_type}`"
                )
                result = await tx.run(query, entity_id=node_id, properties=properties)
                await result.consume()

            await session.execute_write(execute_upsert)
    except Exception as exc:
        logger.error("[%s] Error during upsert_node: %s", self.workspace, exc)
        raise


async def _patched_upsert_nodes_batch(
    self,
    nodes: list[tuple[str, dict[str, str]]],
) -> None:
    """Drop-in replacement that groups nodes by entity_type, one batch per type.

    Each batch runs as a single UNWIND transaction so the round-trip cost stays
    at O(distinct entity types) rather than O(nodes).
    """
    if not nodes:
        return

    workspace_label = self._get_workspace_label()

    # Group by sanitized entity_type
    by_type: dict[str, list[dict]] = defaultdict(list)
    for node_id, node_data in nodes:
        if "entity_id" not in node_data:
            raise ValueError(
                "Neo4j: node properties must contain an 'entity_id' field"
            )
        entity_type = _sanitize_label(
            str(node_data.get("entity_type") or "UNKNOWN")
        )
        by_type[entity_type].append({"entity_id": node_id, "props": node_data})

    try:
        async with self._driver.session(database=self._DATABASE) as session:
            for entity_type, nodes_data in by_type.items():

                async def execute_batch(
                    tx,
                    _nodes=nodes_data,
                    _et=entity_type,
                ) -> None:
                    query = (
                        f"UNWIND $nodes AS row\n"
                        f"MERGE (n:`{workspace_label}` {{entity_id: row.entity_id}})\n"
                        f"SET n += row.props\n"
                        f"SET n:`{_et}`"
                    )
                    result = await tx.run(query, nodes=_nodes)
                    await result.consume()

                await session.execute_write(execute_batch)
    except Exception as exc:
        logger.error(
            "[%s] Error during upsert_nodes_batch: %s", self.workspace, exc
        )
        raise


# ---------------------------------------------------------------------------
# Install / backfill
# ---------------------------------------------------------------------------


def install_neo4j_entity_label_patch() -> None:
    """Monkey-patch ``Neo4JStorage`` to restore entity-type Neo4j labels.

    Idempotent: calling more than once is a no-op.
    Only applied when Neo4JStorage is available in the environment.
    """
    global _PATCH_APPLIED
    if _PATCH_APPLIED:
        return

    try:
        from lightrag.kg.neo4j_impl import Neo4JStorage
    except ImportError:
        logger.debug("Neo4JStorage not available; skipping entity-label patch")
        return

    # Guard: only patch if the current version lacks the SET n:`{entity_type}` line.
    # We detect this by inspecting the source of upsert_node.
    import inspect

    src = inspect.getsource(Neo4JStorage.upsert_node)
    if "SET n:`{entity_type}`" in src or "SET n:`" in src:
        logger.debug(
            "Neo4JStorage.upsert_node already writes entity-type labels; skipping patch"
        )
        _PATCH_APPLIED = True
        return

    Neo4JStorage.upsert_node = _patched_upsert_node
    Neo4JStorage.upsert_nodes_batch = _patched_upsert_nodes_batch
    _PATCH_APPLIED = True
    logger.info(
        "Applied neo4j_entity_label_patch: entity_type will be written as a "
        "Neo4j label on every node (restores LightRAG 1.4.13 behaviour)"
    )


async def backfill_entity_type_labels(
    driver: "AsyncDriver",
    database: str,
    workspace: str,
) -> int:
    """Add entity-type Neo4j labels to nodes that were written without them.

    Queries all distinct entity_type values in the workspace, then for each
    type runs a targeted MATCH+SET to stamp the label.  Safe to run multiple
    times (SET on an already-labelled node is a no-op).

    Returns the number of entity types processed.
    """
    async with driver.session(database=database, default_access_mode="READ") as session:
        result = await session.run(
            f"MATCH (n:`{workspace}`) WHERE n.entity_type IS NOT NULL "
            f"RETURN collect(DISTINCT n.entity_type) AS types"
        )
        record = await result.single()
        await result.consume()
        types: list[str] = record["types"] if record else []

    if not types:
        logger.info("[%s] backfill: no entity_type values found — nothing to do", workspace)
        return 0

    logger.info(
        "[%s] backfill: stamping labels for %d entity type(s): %s",
        workspace,
        len(types),
        types,
    )

    processed = 0
    for raw_type in types:
        entity_type = _sanitize_label(raw_type)
        async with driver.session(database=database) as session:
            result = await session.run(
                f"MATCH (n:`{workspace}`) WHERE n.entity_type = $et "
                f"SET n:`{entity_type}` "
                f"RETURN count(n) AS stamped",
                et=raw_type,
            )
            record = await result.single()
            await result.consume()
            stamped = record["stamped"] if record else 0
            logger.info(
                "[%s] backfill: %d nodes stamped with label '%s'",
                workspace,
                stamped,
                entity_type,
            )
        processed += 1

    logger.info("[%s] backfill complete — %d type(s) processed", workspace, processed)
    return processed
