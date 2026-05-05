"""
VDB Sync Module - Syncs algorithm-discovered relationships to LightRAG VDBs

Issue #65: P0 - Critical architecture gap fix

PROBLEM:
The 8 semantic post-processing algorithms discover relationships and write them
to Neo4j only. LightRAG's VDBs (entity_vdb, relationships_vdb) are NOT updated.
This means agent queries via /query endpoint miss algorithm discoveries.

SOLUTION:
After algorithm execution completes, sync the new relationships back to LightRAG
using the native insert_custom_kg() method. This updates:
- relationships_vdb: For relationship-based retrieval
- Entity descriptions: For better entity retrieval

ARCHITECTURE:
    Document → LightRAG extraction → VDBs updated ✅
                    ↓
             Neo4j sync
                    ↓
             3 Algorithms discover relationships → Neo4j updated ✅
                    ↓
             sync_discoveries_to_vdb() → VDBs UPDATED ✅  ← NEW
                    ↓
             Queries NOW FIND algorithm discoveries ✅
"""

import logging
from typing import Dict, List

from src.ontology.schema import normalize_relationship_type

logger = logging.getLogger(__name__)


async def sync_discoveries_to_vdb(
    neo4j_io,
    relationships_inferred: int = 0
) -> Dict:
    """
    Sync algorithm-discovered relationships from Neo4j back to LightRAG VDBs.
    
    Uses LightRAG's native insert_custom_kg() method which properly updates
    both the relationships_vdb and entity_vdb with new data.
    
    Args:
        neo4j_io: Neo4jGraphIO instance with access to the workspace
        relationships_inferred: Number of new relationships (for validation)
        
    Returns:
        Dict with sync statistics:
        - relationships_synced: Number synced to VDB
        - status: "success" or "error"
        - error: Error message if failed
    """
    # Import here to avoid circular imports
    from src.server.initialization import get_rag_instance
    
    rag_instance = get_rag_instance()
    if not rag_instance:
        logger.warning("⚠️ RAG instance not available - skipping VDB sync")
        return {
            "status": "skipped",
            "reason": "RAG instance not initialized",
            "relationships_synced": 0
        }
    
    # Access the underlying LightRAG instance
    lightrag = rag_instance.lightrag
    if not lightrag:
        logger.warning("⚠️ LightRAG instance not available - skipping VDB sync")
        return {
            "status": "skipped", 
            "reason": "LightRAG not initialized",
            "relationships_synced": 0
        }
    
    try:
        # Get newly inferred relationships from Neo4j
        # These are marked with source='semantic_post_processor'
        new_relationships = _get_inferred_relationships(neo4j_io)
        
        if not new_relationships:
            logger.info("📊 No inferred relationships to sync to VDB")
            return {
                "status": "success",
                "relationships_synced": 0,
                "message": "No relationships to sync"
            }
        
        logger.info(f"🔄 Syncing {len(new_relationships)} inferred relationships to LightRAG VDBs...")
        
        # Build custom_kg structure for LightRAG's insert_custom_kg()
        # Format from LightRAG docs: src_id/tgt_id use entity_name (not Neo4j elementId)
        # 
        # IMPORTANT: LightRAG's ainsert_custom_kg() expects source_id in relationships
        # to be a LABEL that maps to an entry in custom_kg["chunks"]. It builds a lookup:
        #   chunk_to_source_map[chunk["source_id"]] = compute_mdhash_id(chunk["content"])
        # Then for relationships: source_id = chunk_to_source_map.get(rel["source_id"], "UNKNOWN")
        # 
        # Since our inferred relationships don't have original chunk text, we provide
        # a synthetic placeholder chunk with label "semantic_inference" to satisfy the lookup.
        # This eliminates UNKNOWN warnings while correctly marking provenance.
        
        source_label = "semantic_inference"
        
        custom_kg = {
            # Synthetic chunk to satisfy LightRAG's chunk_to_source_map lookup
            "chunks": [
                {
                    "content": "Relationships inferred by semantic post-processing algorithms analyzing entity co-occurrence, document structure, and domain ontology.",
                    "source_id": source_label,
                    "file_path": "semantic_inference"
                }
            ],
            "entities": [],  # Entities already exist - no new ones to add
            "relationships": [
                {
                    "src_id": rel["source_name"],
                    "tgt_id": rel["target_name"],
                    "description": rel.get("reasoning", f"{rel['relationship_type']} relationship"),
                    "keywords": normalize_relationship_type(
                        rel.get("relationship_type", "RELATED_TO")
                    ),
                    "weight": rel.get("confidence", 1.0),
                    "source_id": source_label,  # Must match chunk label for lookup
                    "file_path": "semantic_inference"  # Marks provenance as algorithm-derived
                }
                for rel in new_relationships
            ]
        }
        
        # Use LightRAG's native ASYNC method to insert into VDBs
        # This handles:
        # - Adding to relationships_vdb with proper embeddings
        # - Updating entity descriptions if needed
        # - Maintaining graph consistency
        # NOTE: Must use ainsert_custom_kg (async) not insert_custom_kg (sync wrapper)
        await lightrag.ainsert_custom_kg(custom_kg)
        
        logger.info(f"✅ Synced {len(new_relationships)} relationships to LightRAG VDBs")
        logger.info("   → Agent queries will now find algorithm-discovered relationships")
        
        return {
            "status": "success",
            "relationships_synced": len(new_relationships),
            "message": f"Synced {len(new_relationships)} relationships to VDBs"
        }
        
    except Exception as e:
        logger.error(f"❌ VDB sync failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "relationships_synced": 0
        }


def _get_inferred_relationships(neo4j_io) -> List[Dict]:
    """
    Fetch relationships created by semantic post-processing from Neo4j.
    
    These are identified by:
    - Relationship type: INFERRED_RELATIONSHIP
    - Property: source = 'semantic_post_processor'
    
    Returns:
        List of relationship dicts with source_name, target_name, relationship_type,
        reasoning and confidence.
    """
    query = f"""
    MATCH (source:`{neo4j_io.workspace}`)-[r:INFERRED_RELATIONSHIP]->(target:`{neo4j_io.workspace}`)
    WHERE r.source = 'semantic_post_processor'
    RETURN source.entity_id as source_name,
           target.entity_id as target_name,
           r.type as relationship_type,
           r.reasoning as reasoning,
           r.confidence as confidence,
           r.created_at as created_at
    """
    
    with neo4j_io.driver.session(database=neo4j_io.database) as session:
        result = session.run(query)
        relationships = []
        for record in result:
            relationships.append({
                'source_name': record['source_name'],
                'target_name': record['target_name'],
                'relationship_type': record['relationship_type'],
                'reasoning': record['reasoning'],
                'confidence': record['confidence'] or 1.0
            })
        
        logger.info(f"  📊 Found {len(relationships)} inferred relationships in Neo4j")
        return relationships
