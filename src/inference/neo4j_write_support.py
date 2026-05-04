"""Pure helper logic for Neo4j write-path reporting."""

from __future__ import annotations

from typing import Any


def log_rejected_relationships(
    relationships: list[dict[str, Any]],
    rejected_relationships: list[dict[str, Any]],
    *,
    logger,
) -> None:
    """Log malformed inferred relationships rejected before DB write."""
    if not rejected_relationships:
        return

    logger.error("=" * 80)
    logger.error("❌ CRITICAL: REJECTED MALFORMED RELATIONSHIPS (DATA LOSS)")
    logger.error("=" * 80)
    logger.error(
        f"Rejected {len(rejected_relationships)} of {len(relationships)} relationships due to null/empty 'relationship_type'"
    )
    logger.error("")
    logger.error("REJECTED RELATIONSHIPS:")
    for index, relationship in enumerate(rejected_relationships, 1):
        logger.error(f"  [{index}] Source: {relationship.get('source_id', 'MISSING')}")
        logger.error(f"      Target: {relationship.get('target_id', 'MISSING')}")
        logger.error(
            f"      Type:   {repr(relationship.get('relationship_type', 'MISSING'))}"
        )
        logger.error(f"      Reason: {relationship.get('reasoning', 'N/A')[:100]}")
        logger.error(f"      Full:   {relationship}")
        logger.error("")
    logger.error("=" * 80)
    logger.error("⚠️  INVESTIGATE: Check inference algorithms for null type generation")
    logger.error("=" * 80)


def log_rejected_entities(
    rejected_entities: list[dict[str, Any]],
    *,
    logger,
) -> None:
    """Log malformed entities rejected before DB write."""
    for entity in rejected_entities:
        logger.error(
            f"❌ Critical Error: Entity reached Neo4j without a name! Dropping to prevent DB corruption. Entity: {entity}"
        )

    if rejected_entities:
        logger.warning(
            f"⚠️ Skipped {len(rejected_entities)} entities with missing names in Neo4j creation"
        )