"""Neo4j mutation helpers for semantic post-processing."""

from __future__ import annotations

from typing import Any

from src.inference.neo4j_query_support import run_count_query
from src.inference.neo4j_records import count_from_record, partition_entities_by_name
from src.inference.neo4j_write_support import (
    log_rejected_entities,
    log_rejected_relationships,
)
from src.inference.relationship_payloads import (
    group_retype_updates,
    partition_relationships_by_type,
)


def update_entity_types(
    driver,
    database: str,
    workspace: str,
    entity_updates: list[dict[str, Any]],
    *,
    logger,
) -> int:
    """Update entity types in Neo4j."""
    query = f"""
    UNWIND $updates AS update
    MATCH (n:`{workspace}`)
    WHERE elementId(n) = update.id
    SET n.entity_type = update.new_entity_type,
        n.old_entity_type = n.entity_type,
        n.corrected_by = 'semantic_post_processor',
        n.corrected_at = datetime()
    RETURN count(n) as updated_count
    """

    count = run_count_query(
        driver,
        database,
        query,
        count_from_record,
        "updated_count",
        updates=entity_updates,
    )
    logger.info(f"  ✅ Updated {count} entity types in Neo4j")
    return count


def update_entity_properties(
    driver,
    database: str,
    workspace: str,
    property_updates: list[dict[str, Any]],
    *,
    logger,
) -> int:
    """Update entity properties in Neo4j."""
    query = f"""
    UNWIND $updates AS update
    MATCH (n:`{workspace}`)
    WHERE elementId(n) = update.id
    SET n += update.properties,
        n.enriched_by = 'workload_metadata_enrichment',
        n.enriched_at = datetime()
    RETURN count(n) as updated_count
    """

    count = run_count_query(
        driver,
        database,
        query,
        count_from_record,
        "updated_count",
        updates=property_updates,
    )
    logger.info(f"  ✅ Updated {count} entities with new properties in Neo4j")
    return count


def create_relationships(
    driver,
    database: str,
    workspace: str,
    new_relationships: list[dict[str, Any]],
    *,
    logger,
) -> int:
    """Create inferred relationships in Neo4j."""
    valid_relationships, rejected_relationships = partition_relationships_by_type(
        new_relationships
    )
    log_rejected_relationships(
        new_relationships,
        rejected_relationships,
        logger=logger,
    )

    if not valid_relationships:
        logger.info("  💾 No valid relationships to create")
        return 0

    query = f"""
    UNWIND $relationships AS rel
    MATCH (source:`{workspace}`)
    WHERE elementId(source) = rel.source_id
    MATCH (target:`{workspace}`)
    WHERE elementId(target) = rel.target_id
    MERGE (source)-[r:INFERRED_RELATIONSHIP {{
        type: rel.relationship_type,
        reasoning: rel.reasoning,
        source: 'semantic_post_processor',
        created_at: datetime()
    }}]->(target)
    SET r.confidence = CASE WHEN rel.confidence IS NOT NULL THEN rel.confidence ELSE r.confidence END
    RETURN count(r) as created_count
    """

    with driver.session(database=database) as session:
        result = session.run(query, relationships=valid_relationships)
        record = result.single()
        count = count_from_record(record, "created_count")

    logger.info(f"  💾 Created {count} new relationships in Neo4j")
    return count


def retype_relationships(
    driver,
    database: str,
    workspace: str,
    retype_updates: list[dict[str, Any]],
    *,
    logger,
) -> int:
    """Retype relationships in Neo4j using APOC."""
    if not retype_updates:
        return 0

    batches = group_retype_updates(retype_updates)
    total_retyped = 0
    for (old_type, new_type), updates in batches.items():
        source_ids = [update["source_id"] for update in updates]
        target_ids = [update["target_id"] for update in updates]

        query = f"""
        UNWIND range(0, size($source_ids) - 1) AS idx
        MATCH (a:`{workspace}`)-[r:`{old_type}`]->(b:`{workspace}`)
        WHERE elementId(a) = $source_ids[idx] AND elementId(b) = $target_ids[idx]
        CALL apoc.refactor.setType(r, $new_type)
        YIELD input, output
        SET output.retyped_from = $old_type,
            output.retyped_by = 'generic_relationship_normalizer',
            output.retyped_at = datetime()
        RETURN count(output) as retyped_count
        """

        try:
            with driver.session(database=database) as session:
                result = session.run(
                    query,
                    source_ids=source_ids,
                    target_ids=target_ids,
                    new_type=new_type,
                )
                record = result.single()
                count = count_from_record(record, "retyped_count")
                total_retyped += count
                if count > 0:
                    logger.info(
                        f"    Retyped {count} relationships: {old_type} -> {new_type}"
                    )
        except Exception as exc:
            logger.warning(
                f"    ⚠️ Failed to retype {old_type} -> {new_type}: {exc}"
            )

    if total_retyped > 0:
        logger.info(f"  ✅ Retyped {total_retyped} relationships in Neo4j")
    return total_retyped


def enrich_entity_metadata(
    driver,
    database: str,
    workspace: str,
    metadata_updates: list[dict[str, Any]],
    *,
    logger,
) -> int:
    """Add metadata properties to entities in Neo4j."""
    query = f"""
    UNWIND $updates AS update
    MATCH (n:`{workspace}`)
    WHERE elementId(n) = update.id
    SET n += update.metadata,
        n.metadata_updated_by = 'semantic_post_processor',
        n.metadata_updated_at = datetime()
    RETURN count(n) as enriched_count
    """

    with driver.session(database=database) as session:
        result = session.run(query, updates=metadata_updates)
        record = result.single()
        count = count_from_record(record, "enriched_count")

    logger.info(f"  ✅ Enriched {count} entities with metadata in Neo4j")
    return count


def create_entities(
    driver,
    database: str,
    workspace: str,
    entities: list[dict[str, Any]],
    *,
    logger,
) -> int:
    """Create or merge entities in Neo4j."""
    valid_entities, rejected_entities = partition_entities_by_name(entities)
    log_rejected_entities(rejected_entities, logger=logger)

    if not valid_entities:
        logger.info("  💾 No valid entities to create")
        return 0

    query = f"""
    UNWIND $entities AS entity
    MERGE (n:`{workspace}` {{entity_name: entity.entity_name}})
    SET n.entity_type = entity.entity_type,
        n.created_by = 'lightrag_native',
        n.created_at = datetime()

    FOREACH (_ IN CASE WHEN entity.entity_type = 'requirement' THEN [1] ELSE [] END |
        SET n.criticality = entity.criticality,
            n.modal_verb = entity.modal_verb,
            n.req_type = entity.req_type,
            n.labor_drivers = entity.labor_drivers,
            n.material_needs = entity.material_needs
    )
    FOREACH (_ IN CASE WHEN entity.entity_type = 'evaluation_factor' THEN [1] ELSE [] END |
        SET n.weight = entity.weight,
            n.importance = entity.importance,
            n.subfactors = entity.subfactors
    )
    FOREACH (_ IN CASE WHEN entity.entity_type = 'proposal_instruction' THEN [1] ELSE [] END |
        SET n.page_limit = entity.page_limit,
            n.format_reqs = entity.format_reqs,
            n.volume = entity.volume
    )
    FOREACH (_ IN CASE WHEN entity.entity_type = 'clause' THEN [1] ELSE [] END |
        SET n.clause_number = entity.clause_number,
            n.regulation = entity.regulation
    )
    FOREACH (_ IN CASE WHEN entity.entity_type = 'performance_standard' THEN [1] ELSE [] END |
        SET n.threshold = entity.threshold,
            n.measurement_method = entity.measurement_method
    )
    FOREACH (_ IN CASE WHEN entity.entity_type = 'strategic_theme' THEN [1] ELSE [] END |
        SET n.theme_type = entity.theme_type
    )

    RETURN count(n) as created_count
    """

    count = run_count_query(
        driver,
        database,
        query,
        count_from_record,
        "created_count",
        entities=valid_entities,
    )
    logger.info(f"  💾 Created/Merged {count} entities in Neo4j")
    return count


def create_typed_relationships(
    driver,
    database: str,
    workspace: str,
    relationships: list[dict[str, Any]],
    *,
    logger,
) -> int:
    """Create typed relationships in Neo4j using APOC for dynamic types."""
    query = f"""
    UNWIND $relationships AS rel
    MATCH (source:`{workspace}` {{entity_name: rel.source_entity}})
    MATCH (target:`{workspace}` {{entity_name: rel.target_entity}})
    CALL apoc.create.relationship(source, rel.relationship_type, {{
        description: rel.relationship_type,
        source: 'lightrag_native',
        created_at: datetime()
    }}, target) YIELD rel as r
    RETURN count(r) as created_count
    """

    count = run_count_query(
        driver,
        database,
        query,
        count_from_record,
        "created_count",
        relationships=relationships,
    )
    logger.info(f"  💾 Created {count} typed relationships in Neo4j")
    return count


__all__ = [
    "create_entities",
    "create_relationships",
    "create_typed_relationships",
    "enrich_entity_metadata",
    "retype_relationships",
    "update_entity_properties",
    "update_entity_types",
]
