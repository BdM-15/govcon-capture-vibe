"""
Neo4j Knowledge Graph I/O Operations

Handles reading and writing to Neo4j database for the knowledge graph.
Provides clean interfaces for semantic relationship inference and post-processing.
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List

from neo4j import GraphDatabase

from src.core import get_settings
from src.inference.relationship_payloads import (
    group_retype_updates,
    partition_relationships_by_type,
)

logger = logging.getLogger(__name__)


def entity_record_to_dict(record: Any) -> dict[str, Any]:
    """Convert a Neo4j entity row into the post-processing entity contract."""
    entity_id = record.get("entity_id")
    entity_name = record.get("entity_name")
    canonical_name = str(entity_name or entity_id or "").strip()
    return {
        "id": record["id"],
        "entity_id": entity_id,
        "entity_name": canonical_name or entity_name,
        "entity_type": record["entity_type"],
        "description": record["description"],
        "source_id": record["source_id"],
    }


def relationship_record_to_dict(record: Any) -> dict[str, Any]:
    """Convert a Neo4j relationship row into the post-processing edge contract."""
    return {
        "source": record["source"],
        "target": record["target"],
        "type": record["rel_type"],
        "weight": record["weight"],
        "description": record["description"],
        "keywords": record["keywords"],
    }


def type_counts_from_records(records: Any) -> dict[str, int]:
    """Convert rows with type/count fields into a count mapping."""
    return {record["type"]: record["count"] for record in records}


def entity_names_from_records(records: Any) -> list[str]:
    """Extract entity_name values from Neo4j rows."""
    return [record["entity_name"] for record in records]


def count_from_record(record: Any | None, key: str) -> int:
    """Read an integer count from a single Neo4j row."""
    if not record:
        return 0
    return int(record[key] or 0)


def partition_entities_by_name(
    entities: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split entity payloads into named and rejected groups."""
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for entity in entities:
        if entity.get("entity_name"):
            valid.append(entity)
        else:
            rejected.append(entity)
    return valid, rejected


def group_entities_by_type(
    entities: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group entities by lowercase entity type for efficient batching."""
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in entities:
        entity_type = str(entity.get("entity_type") or "").lower()
        grouped[entity_type].append(entity)
    return dict(grouped)


def run_mapped_query(
    driver: Any,
    database: str,
    query: str,
    row_mapper: Any,
    **params: Any,
) -> list[Any]:
    """Run query and map each row through ``row_mapper``."""
    with driver.session(database=database) as session:
        result = session.run(query, **params)
        return [row_mapper(record) for record in result]


def run_projected_query(
    driver: Any,
    database: str,
    query: str,
    projector: Any,
    **params: Any,
) -> Any:
    """Run query and project full result through ``projector``."""
    with driver.session(database=database) as session:
        result = session.run(query, **params)
        return projector(result)


def run_count_query(
    driver: Any,
    database: str,
    query: str,
    count_reader: Any,
    result_key: str,
    **params: Any,
) -> int:
    """Run query returning one count row and read it with ``count_reader``."""
    with driver.session(database=database) as session:
        result = session.run(query, **params)
        return count_reader(result.single(), result_key)


def log_rejected_relationships(
    relationships: list[dict[str, Any]],
    rejected_relationships: list[dict[str, Any]],
    *,
    logger: logging.Logger,
) -> None:
    """Log malformed inferred relationships rejected before DB write."""
    if not rejected_relationships:
        return

    logger.error("=" * 80)
    logger.error("❌ CRITICAL: REJECTED MALFORMED RELATIONSHIPS (DATA LOSS)")
    logger.error("=" * 80)
    logger.error(
        "Rejected %s of %s relationships due to null/empty 'relationship_type'",
        len(rejected_relationships),
        len(relationships),
    )
    logger.error("")
    logger.error("REJECTED RELATIONSHIPS:")
    for index, relationship in enumerate(rejected_relationships, 1):
        logger.error("  [%s] Source: %s", index, relationship.get("source_id", "MISSING"))
        logger.error("      Target: %s", relationship.get("target_id", "MISSING"))
        logger.error("      Type:   %r", relationship.get("relationship_type", "MISSING"))
        logger.error("      Reason: %s", relationship.get("reasoning", "N/A")[:100])
        logger.error("      Full:   %s", relationship)
        logger.error("")
    logger.error("=" * 80)
    logger.error("⚠️  INVESTIGATE: Check inference algorithms for null type generation")
    logger.error("=" * 80)


def log_rejected_entities(
    rejected_entities: list[dict[str, Any]],
    *,
    logger: logging.Logger,
) -> None:
    """Log malformed entities rejected before DB write."""
    for entity in rejected_entities:
        logger.error(
            "❌ Critical Error: Entity reached Neo4j without a name! Dropping to prevent DB corruption. Entity: %s",
            entity,
        )

    if rejected_entities:
        logger.warning(
            "⚠️ Skipped %s entities with missing names in Neo4j creation",
            len(rejected_entities),
        )


class Neo4jGraphIO:
    """Neo4j graph I/O operations for semantic post-processing"""
    
    def __init__(self):
        """Initialize Neo4j connection from centralized settings"""
        settings = get_settings()
        self.uri = settings.neo4j_uri
        self.username = settings.neo4j_username
        self.password = settings.neo4j_password
        self.database = settings.neo4j_database
        self.workspace = settings.neo4j_workspace
        
        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.username, self.password)
        )
    
    def close(self):
        """Close Neo4j connection"""
        if self.driver:
            self.driver.close()
    
    def get_all_entities(self) -> List[Dict]:
        """
        Fetch all entities from Neo4j workspace.
        
        Returns:
            List of entity dicts with keys: id, entity_name, entity_type, description
        """
        query = f"""
        MATCH (n:`{self.workspace}`)
        RETURN elementId(n) as id,
               n.entity_id as entity_id,
               n.entity_name as entity_name,
               n.entity_type as entity_type,
               n.description as description,
               n.source_id as source_id
        """

        entities = run_mapped_query(
            self.driver,
            self.database,
            query,
            entity_record_to_dict,
        )
        logger.info(f"  📊 Fetched {len(entities)} entities from Neo4j")
        return entities
    
    def get_all_relationships(self) -> List[Dict]:
        """
        Fetch all relationships from Neo4j workspace.
        
        Returns:
            List of relationship dicts with keys: source, target, type, weight, description
        """
        query = f"""
        MATCH (a:`{self.workspace}`)-[r]->(b:`{self.workspace}`)
        RETURN elementId(a) as source,
               elementId(b) as target,
               type(r) as rel_type,
               r.weight as weight,
               r.description as description,
               r.keywords as keywords
        """

        relationships = run_mapped_query(
            self.driver,
            self.database,
            query,
            relationship_record_to_dict,
        )
        logger.info(f"  📊 Fetched {len(relationships)} relationships from Neo4j")
        return relationships
    
    def get_orphaned_entity_ids(self) -> List[str]:
        """
        Find entities that have no relationships (true orphans).
        
        Returns:
            List of entity_name values for entities with no incoming or outgoing relationships
        """
        query = f"""
        MATCH (n:`{self.workspace}`)
        WHERE NOT (n)-[]-()
        RETURN n.entity_id as entity_name
        """

        orphan_names = run_projected_query(
            self.driver,
            self.database,
            query,
            entity_names_from_records,
        )
        if orphan_names:
            logger.info(f"  📊 Found {len(orphan_names)} truly orphaned entities in Neo4j")
        return orphan_names
    
    def update_entity_types(self, entity_updates: List[Dict]) -> int:
        """
        Update entity types in Neo4j.
        
        Args:
            entity_updates: List of dicts with 'id' and 'new_entity_type' keys
            
        Returns:
            Number of entities updated
        """
        query = f"""
        UNWIND $updates AS update
        MATCH (n:`{self.workspace}`)
        WHERE elementId(n) = update.id
        SET n.entity_type = update.new_entity_type,
            n.old_entity_type = n.entity_type,
            n.corrected_by = 'semantic_post_processor',
            n.corrected_at = datetime()
        RETURN count(n) as updated_count
        """

        count = run_count_query(
            self.driver,
            self.database,
            query,
            count_from_record,
            "updated_count",
            updates=entity_updates,
        )
        logger.info(f"  ✅ Updated {count} entity types in Neo4j")
        return count
    
    def update_entity_properties(self, property_updates: List[Dict]) -> int:
        """
        Update entity properties in Neo4j (for workload metadata enrichment).
        
        Args:
            property_updates: List of dicts with 'id' and 'properties' keys
                - id: Entity elementId
                - properties: Dict of property_name → property_value
                
        Returns:
            Number of entities updated
        """
        query = f"""
        UNWIND $updates AS update
        MATCH (n:`{self.workspace}`)
        WHERE elementId(n) = update.id
        SET n += update.properties,
            n.enriched_by = 'workload_metadata_enrichment',
            n.enriched_at = datetime()
        RETURN count(n) as updated_count
        """

        count = run_count_query(
            self.driver,
            self.database,
            query,
            count_from_record,
            "updated_count",
            updates=property_updates,
        )
        logger.info(f"  ✅ Updated {count} entities with new properties in Neo4j")
        return count

    def update_entity_names(self, entity_updates: List[Dict]) -> int:
        """
        Canonicalize entity names in Neo4j without changing node identity.

        Args:
            entity_updates: List of dicts with ``id`` and ``new_entity_name`` keys.

        Returns:
            Number of entities updated.
        """
        query = f"""
        UNWIND $updates AS update
        MATCH (n:`{self.workspace}`)
        WHERE elementId(n) = update.id
        WITH n, update, coalesce(n.entity_name, n.entity_id) AS old_name
        SET n.old_entity_name = old_name,
            n.entity_id = update.new_entity_name,
            n.entity_name = update.new_entity_name,
            n.normalized_by = 'semantic_post_processor',
            n.normalized_at = datetime()
        RETURN count(n) as updated_count
        """

        count = run_count_query(
            self.driver,
            self.database,
            query,
            count_from_record,
            "updated_count",
            updates=entity_updates,
        )
        logger.info(f"  ✅ Canonicalized {count} entity names in Neo4j")
        return count
    
    def create_relationships(self, new_relationships: List[Dict]) -> int:
        """
        Create new relationships in Neo4j.
        
        Args:
            new_relationships: List of relationship dicts with keys:
                - source_id: Entity ID for source node (elementId)
                - target_id: Entity ID for target node (elementId)
                - relationship_type: Type of relationship
                - reasoning: Human-readable explanation
                - confidence: Optional confidence score (0.0-1.0)
                
        Returns:
            Number of relationships created
        """
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
        MATCH (source:`{self.workspace}`)
        WHERE elementId(source) = rel.source_id
        MATCH (target:`{self.workspace}`)
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

        with self.driver.session(database=self.database) as session:
            result = session.run(query, relationships=valid_relationships)
            record = result.single()
            count = count_from_record(record, "created_count")

        logger.info(f"  💾 Created {count} new relationships in Neo4j")
        return count
    
    def retype_relationships(self, retype_updates: List[Dict]) -> int:
        """
        Retype relationships in Neo4j using APOC.
        
        Neo4j relationship types are immutable labels, so this uses
        apoc.refactor.setType to change the label in-place.
        
        Args:
            retype_updates: List of dicts with:
                - source_id: elementId of source node
                - target_id: elementId of target node
                - old_type: current relationship type label
                - new_type: desired relationship type label
                
        Returns:
            Number of relationships retyped
        """
        if not retype_updates:
            return 0

        batches = group_retype_updates(retype_updates)
        total_retyped = 0
        for (old_type, new_type), updates in batches.items():
            source_ids = [update["source_id"] for update in updates]
            target_ids = [update["target_id"] for update in updates]

            query = f"""
            UNWIND range(0, size($source_ids) - 1) AS idx
            MATCH (a:`{self.workspace}`)-[r:`{old_type}`]->(b:`{self.workspace}`)
            WHERE elementId(a) = $source_ids[idx] AND elementId(b) = $target_ids[idx]
            CALL apoc.refactor.setType(r, $new_type)
            YIELD input, output
            SET output.retyped_from = $old_type,
                output.retyped_by = 'generic_relationship_normalizer',
                output.retyped_at = datetime()
            RETURN count(output) as retyped_count
            """

            try:
                with self.driver.session(database=self.database) as session:
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

    def enrich_entity_metadata(self, metadata_updates: List[Dict]) -> int:
        """
        Add metadata properties to entities in Neo4j.
        
        Args:
            metadata_updates: List of dicts with 'id' and metadata properties
            
        Returns:
            Number of entities enriched
        """
        query = f"""
        UNWIND $updates AS update
        MATCH (n:`{self.workspace}`)
        WHERE elementId(n) = update.id
        SET n += update.metadata,
            n.metadata_updated_by = 'semantic_post_processor',
            n.metadata_updated_at = datetime()
        RETURN count(n) as enriched_count
        """

        with self.driver.session(database=self.database) as session:
            result = session.run(query, updates=metadata_updates)
            record = result.single()
            count = count_from_record(record, "enriched_count")

        logger.info(f"  ✅ Enriched {count} entities with metadata in Neo4j")
        return count
    
    def get_entity_count_by_type(self) -> Dict[str, int]:
        """
        Get count of entities by type.
        
        Returns:
            Dict mapping entity_type to count
        """
        query = f"""
        MATCH (n:`{self.workspace}`)
        WHERE n.entity_type IS NOT NULL
        RETURN n.entity_type as type, count(n) as count
        ORDER BY count DESC
        """

        return run_projected_query(
            self.driver,
            self.database,
            query,
            type_counts_from_records,
        )
    
    def get_relationship_count_by_type(self) -> Dict[str, int]:
        """
        Get count of relationships by type.
        
        Returns:
            Dict mapping relationship_type to count
        """
        query = f"""
        MATCH (a:`{self.workspace}`)-[r]->(b:`{self.workspace}`)
        RETURN type(r) as type, count(r) as count
        ORDER BY count DESC
        """

        return run_projected_query(
            self.driver,
            self.database,
            query,
            type_counts_from_records,
        )

    def create_entities(self, entities: List[Dict]) -> int:
        """Create or merge entities in Neo4j."""
        valid_entities, rejected_entities = partition_entities_by_name(entities)
        log_rejected_entities(rejected_entities, logger=logger)

        if not valid_entities:
            logger.info("  💾 No valid entities to create")
            return 0

        query = f"""
        UNWIND $entities AS entity
        MERGE (n:`{self.workspace}` {{entity_name: entity.entity_name}})
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
            self.driver,
            self.database,
            query,
            count_from_record,
            "created_count",
            entities=valid_entities,
        )
        logger.info(f"  💾 Created/Merged {count} entities in Neo4j")
        return count

    def create_typed_relationships(self, relationships: List[Dict]) -> int:
        """Create typed relationships in Neo4j using APOC for dynamic types."""
        query = f"""
        UNWIND $relationships AS rel
        MATCH (source:`{self.workspace}` {{entity_name: rel.source_entity}})
        MATCH (target:`{self.workspace}` {{entity_name: rel.target_entity}})
        CALL apoc.create.relationship(source, rel.relationship_type, {{
            description: rel.relationship_type,
            source: 'lightrag_native',
            created_at: datetime()
        }}, target) YIELD rel as r
        RETURN count(r) as created_count
        """

        count = run_count_query(
            self.driver,
            self.database,
            query,
            count_from_record,
            "created_count",
            relationships=relationships,
        )
        logger.info(f"  💾 Created {count} typed relationships in Neo4j")
        return count


__all__ = ["Neo4jGraphIO", "group_entities_by_type"]
