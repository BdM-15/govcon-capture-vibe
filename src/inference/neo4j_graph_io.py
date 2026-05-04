"""
Neo4j Knowledge Graph I/O Operations

Handles reading and writing to Neo4j database for the knowledge graph.
Provides clean interfaces for semantic relationship inference and post-processing.
"""

import logging
from typing import List, Dict
from neo4j import GraphDatabase

from src.core import get_settings
from src.inference.neo4j_records import (
    count_from_record,
    entity_names_from_records,
    entity_record_to_dict,
    group_entities_by_type,
    partition_entities_by_name,
    relationship_record_to_dict,
    type_counts_from_records,
)
from src.inference.relationship_payloads import (
    group_retype_updates,
    partition_relationships_by_type,
)
from src.inference.neo4j_query_support import (
    run_count_query,
    run_mapped_query,
    run_projected_query,
)
from src.inference.neo4j_write_support import (
    log_rejected_entities,
    log_rejected_relationships,
)

logger = logging.getLogger(__name__)


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
               n.entity_id as entity_name,
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
            'updated_count',
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
            'updated_count',
            updates=property_updates,
        )
        logger.info(f"  ✅ Updated {count} entities with new properties in Neo4j")
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
        # Filter out relationships with missing/null/empty relationship_type
        # (prevents Neo4j ClientError: cannot merge relationship with null type)
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
        
        # Neo4j doesn't allow dynamic relationship types in pure Cypher
        # We need to use APOC or create with a property
        # Only include confidence if present (trust LLM quality like LightRAG)
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
            count = count_from_record(record, 'created_count')
            
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
        
        # Group by (old_type, new_type) for batch processing
        batches = group_retype_updates(retype_updates)
        
        total_retyped = 0
        for (old_type, new_type), updates in batches.items():
            source_ids = [u['source_id'] for u in updates]
            target_ids = [u['target_id'] for u in updates]
            
            # Use APOC to retype relationships in batch
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
                        new_type=new_type
                    )
                    record = result.single()
                    count = count_from_record(record, 'retyped_count')
                    total_retyped += count
                    if count > 0:
                        logger.info(f"    Retyped {count} relationships: {old_type} → {new_type}")
            except Exception as e:
                logger.warning(f"    ⚠️ Failed to retype {old_type} → {new_type}: {e}")
        
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
            count = count_from_record(record, 'enriched_count')
            
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
        """
        Create new entities in Neo4j.
        
        Args:
            entities: List of entity dicts (from LightRAG native extraction)
        
        Returns:
            Number of entities created
        """
        # Filter out any entities that might have slipped through with None names
        # Note: LightRAG native extraction handles this, but this is a safety net.
        valid_entities, rejected_entities = partition_entities_by_name(entities)
        log_rejected_entities(rejected_entities, logger=logger)

        if not valid_entities:
            logger.info("  💾 No valid entities to create")
            return 0
        
        # Note: We use MERGE on entity_name to avoid duplicates
        query = f"""
        UNWIND $entities AS entity
        MERGE (n:`{self.workspace}` {{entity_name: entity.entity_name}})
        SET n.entity_type = entity.entity_type,
            n.created_by = 'lightrag_native',
            n.created_at = datetime()
        
        // Set specific properties based on type
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
            'created_count',
            entities=valid_entities,
        )
        logger.info(f"  💾 Created/Merged {count} entities in Neo4j")
        return count

    def create_typed_relationships(self, relationships: List[Dict]) -> int:
        """
        Create typed relationships in Neo4j using APOC for dynamic types.
        
        Args:
            relationships: List of dicts with source_entity, target_entity, relationship_type, description
        """
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
            'created_count',
            relationships=relationships,
        )
        logger.info(f"  💾 Created {count} typed relationships in Neo4j")
        return count


__all__ = ["Neo4jGraphIO", "group_entities_by_type"]
