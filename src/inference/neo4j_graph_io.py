"""
Neo4j Knowledge Graph I/O Operations

Handles reading and writing to Neo4j database for the knowledge graph.
Provides clean interfaces for semantic relationship inference and post-processing.
"""

import logging
from typing import List, Dict

from neo4j import GraphDatabase

from src.core import get_settings
from src.inference.neo4j_mutations import (
    create_entities,
    create_relationships,
    create_typed_relationships,
    enrich_entity_metadata,
    retype_relationships,
    update_entity_properties,
    update_entity_types,
)
from src.inference.neo4j_records import (
    entity_names_from_records,
    entity_record_to_dict,
    group_entities_by_type,
    relationship_record_to_dict,
    type_counts_from_records,
)
from src.inference.neo4j_query_support import (
    run_mapped_query,
    run_projected_query,
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
        return update_entity_types(
            self.driver,
            self.database,
            self.workspace,
            entity_updates,
            logger=logger,
        )
    
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
        return update_entity_properties(
            self.driver,
            self.database,
            self.workspace,
            property_updates,
            logger=logger,
        )
    
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
        return create_relationships(
            self.driver,
            self.database,
            self.workspace,
            new_relationships,
            logger=logger,
        )
    
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
        return retype_relationships(
            self.driver,
            self.database,
            self.workspace,
            retype_updates,
            logger=logger,
        )

    def enrich_entity_metadata(self, metadata_updates: List[Dict]) -> int:
        """
        Add metadata properties to entities in Neo4j.
        
        Args:
            metadata_updates: List of dicts with 'id' and metadata properties
            
        Returns:
            Number of entities enriched
        """
        return enrich_entity_metadata(
            self.driver,
            self.database,
            self.workspace,
            metadata_updates,
            logger=logger,
        )
    
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
        return create_entities(
            self.driver,
            self.database,
            self.workspace,
            entities,
            logger=logger,
        )

    def create_typed_relationships(self, relationships: List[Dict]) -> int:
        """
        Create typed relationships in Neo4j using APOC for dynamic types.
        
        Args:
            relationships: List of dicts with source_entity, target_entity, relationship_type, description
        """
        return create_typed_relationships(
            self.driver,
            self.database,
            self.workspace,
            relationships,
            logger=logger,
        )


__all__ = ["Neo4jGraphIO", "group_entities_by_type"]
