"""
Semantic Post-Processing for Government Contracting RFPs
========================================================

Neo4j-native LLM-powered enhancements to the extracted knowledge graph:

1. **Entity Normalization**: Fix table/hash/unknown entity types
2. **Relationship Normalization**: Re-type generic RELATED_TO via entity-pair lookup
3. **Relationship Inference**: Infer missing semantic relationships using 3 algorithms
4. **Optional Workload Enrichment**: Add BOE metadata to requirements when explicitly enabled
5. **VDB Synchronization**: Sync inferred relationships to LightRAG vector stores

Architecture (Issue #54 - Back to Basics):
- Entity extraction uses native LightRAG with the govcon ontology
- Pydantic validation is used for POST-PROCESSING only (InferredRelationship)
- No Pydantic validation during extraction - LightRAG handles it natively

Usage:
    from src.inference.semantic_post_processor import enhance_knowledge_graph
    
    stats = await enhance_knowledge_graph(
        rag_storage_path="path/to/rag_storage",
        llm_func=my_llm_function
    )
"""

import logging
import time
from typing import Dict, Callable, Awaitable, List

from src.core import get_settings
from src.inference.neo4j_graph_io import Neo4jGraphIO, group_entities_by_type
from src.inference.algorithms import run_all_algorithms_parallel
from src.inference.semantic_post_process_support import (
    build_post_processing_result,
    collect_relationship_retype_updates,
    heuristic_table_type_mapping as _heuristic_table_type_mapping,
)
from src.ontology.schema import VALID_ENTITY_TYPES

logger = logging.getLogger(__name__)

# Convert set to list for prompt generation
ALLOWED_TYPES = list(VALID_ENTITY_TYPES)


def get_semantic_post_processing_config():
    """Get semantic post-processing configuration from centralized settings."""
    settings = get_settings()
    return {
        'max_concurrent_llm_calls': settings.get_effective_post_processing_max_async(),
    }


# Legacy constants for backward compatibility (use get_semantic_post_processing_config() instead)
# These are evaluated at import time for modules that depend on them
_settings = get_settings()
MAX_CONCURRENT_LLM_CALLS = _settings.get_effective_post_processing_max_async()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTITY-PAIR → RELATIONSHIP TYPE MAPPING (Approach B: Generic Relationship Fix)
# ═══════════════════════════════════════════════════════════════════════════════
# When extraction produces generic types (belongs_to, contained_in, part_of)
# that get normalized to RELATED_TO or CHILD_OF, this mapping re-types them
# based on the source and target entity types.
#
# Root cause: Table-derived text from MinerU/VLM has entities co-occurring
# without prose connectors, so the LLM defaults to generic relationships.
# ═══════════════════════════════════════════════════════════════════════════════

# NOTE: _infer_entity_type and _infer_entity_types_parallel REMOVED
# With Pydantic validation in extraction, LLM-based entity type correction is no longer needed.
# Invalid types are caught and coerced during extraction, not post-hoc.
# This saves LLM API costs and processing time.
# NOTE: Algorithm functions moved to src/inference/algorithms/ modules
# Orchestrated by run_all_algorithms_parallel() from src.inference.algorithms



async def _semantic_post_processor_neo4j(
    llm_model_name: str = None,
    temperature: float = 0.1,
    rag_storage_path: str = "./rag_storage",
) -> Dict:
    """
    Neo4j-native semantic post-processing using Cypher queries.
    
    This function:
    1. Reads entities/relationships from Neo4j
    2. Corrects entity types using LLM inference
    3. Infers missing relationships using LLM inference
    4. Writes updates back to Neo4j via Cypher
    
    Args:
        llm_model_name: Name of LLM model to use
        temperature: Temperature for LLM inference
        
    Returns:
        Dict with processing statistics
    """
    settings = get_settings()
    if llm_model_name is None:
        # Use REASONING model for post-processing (grok-4-1 series)
        llm_model_name = settings.post_processing_llm_name
    
    start_time = time.time()
    phase_times = {}  # Track per-phase durations
    
    # Initialize Neo4j I/O
    logger.info("\n📊 Initializing Neo4j connection...")
    neo4j_io = Neo4jGraphIO()
    
    try:
        # Phase 1: Load entities and relationships
        phase_start = time.time()
        logger.info("\n📥 Phase 1 · Data Loading: Reading knowledge graph from Neo4j...")
        entities = neo4j_io.get_all_entities()
        relationships = neo4j_io.get_all_relationships()
        
        # Capture the graph as it enters post-processing. Final reported counts
        # are taken only after Phase 5 so logs do not mix pre/post snapshots.
        starting_entity_count = len(entities)
        starting_rel_count = len(relationships)
        phase_times['Phase 1 · Data Loading'] = time.time() - phase_start
        logger.info(f"  📊 Starting graph snapshot: {starting_entity_count} entities, {starting_rel_count} relationships")
        logger.info(f"  ⏱️  Phase 1 completed in {phase_times['Phase 1 · Data Loading']:.1f}s")
        
        if not entities:
            logger.warning("⚠️  No entities found in Neo4j workspace")
            return {
                "status": "skipped",
                "reason": "no_entities",
                "entities_corrected": 0,
                "relationships_inferred": 0,
                "processing_time": 0
            }
        
        # Phase 2: Lightweight Entity Type Cleanup (NO LLM INFERENCE)
        # ========================================================================
        # With native LightRAG extraction, most types are valid from our ontology.
        # This phase ONLY handles edge cases:
        # 1. "table" from RAG-Anything's multimodal processors (generic type)
        # 2. Hash-prefixed types (#requirement) from LightRAG internal markers
        # 
        # NO LLM calls needed - all corrections are heuristic/deterministic.
        # ========================================================================
        phase_start = time.time()
        logger.info("\n🔧 Phase 2 · Entity Normalization: Lightweight type cleanup...")
        entity_updates = []
        grouped = group_entities_by_type(entities)
        
        table_mapped = 0
        hash_cleaned = 0
        unknown_entities = []  # Collect UNKNOWN entities for LLM retyping
        
        for entity_type, entity_group in grouped.items():
            entity_type_clean = entity_type.lower()
            
            # Strip various prefix formats from LightRAG internal markers
            # Handles: "#requirement", "#|requirement", "|requirement"
            has_hash_prefix = entity_type_clean.startswith('#')
            has_pipe_prefix = entity_type_clean.startswith('|') or entity_type_clean.startswith('#|')
            
            if entity_type_clean.startswith('#|'):
                entity_type_clean = entity_type_clean[2:]  # Strip "#|"
            elif has_hash_prefix:
                entity_type_clean = entity_type_clean[1:]  # Strip "#"
            elif entity_type_clean.startswith('|'):
                entity_type_clean = entity_type_clean[1:]  # Strip "|"
            
            # CASE 1: "table" entities from RAG-Anything multimodal processors
            # These bypass our Pydantic adapter - map based on content heuristically
            if entity_type_clean == 'table':
                logger.info(f"  📊 Processing {len(entity_group)} table entities (from RAG-Anything)...")
                for entity in entity_group:
                    mapped_type = _heuristic_table_type_mapping(entity)
                    if mapped_type:
                        entity_updates.append({
                            'id': entity['id'],
                            'new_entity_type': mapped_type
                        })
                        table_mapped += 1
                    # If can't map, leave as 'concept' (safe default)
                    # NO LLM fallback - extraction should have handled this
                continue
            
            # CASE 2: Prefixed types (#requirement, #|requirement, |requirement) - clean the prefix
            if (has_hash_prefix or has_pipe_prefix) and entity_type_clean in [t.lower() for t in ALLOWED_TYPES]:
                logger.info(f"  🔧 Cleaning {len(entity_group)} '{entity_type}' → '{entity_type_clean}'")
                for entity in entity_group:
                    entity_updates.append({
                        'id': entity['id'],
                        'new_entity_type': entity_type_clean
                    })
                    hash_cleaned += 1
                continue
            
            # CASE 3: "UNKNOWN" entities - created by LightRAG when relationships reference
            # entities that weren't extracted (due to delimiter corruption or missing extraction).
            # These could contain critical workload drivers - retype them with LLM.
            if entity_type_clean == 'unknown':
                unknown_entities.extend(entity_group)
        
        if table_mapped > 0:
            logger.info(f"  ✅ Heuristically mapped {table_mapped} table entities")
        if hash_cleaned > 0:
            logger.info(f"  ✅ Cleaned {hash_cleaned} prefixed entity types (#, #|, |)")
        
        # CASE 3 Processing: LLM retype UNKNOWN entities (could be critical workload drivers)
        unknown_retyped = 0
        if unknown_entities:
            logger.info(f"  🔍 Retyping {len(unknown_entities)} UNKNOWN entities with LLM...")
            from src.inference.entity_operations import retype_entities_batch
            from src.utils.llm_client import call_llm_async
            
            # LLM function wrapper for retyping
            async def llm_func(prompt: str, system_prompt: str) -> str:
                return await call_llm_async(
                    prompt=prompt,
                    model=llm_model_name,
                    system_prompt=system_prompt,
                    temperature=0.1  # Low temp for consistent typing
                )
            
            # Process in batches of 20 to avoid token limits
            batch_size = 20
            for i in range(0, len(unknown_entities), batch_size):
                batch = unknown_entities[i:i+batch_size]
                try:
                    retyped = await retype_entities_batch(batch, llm_func)
                    for entity in batch:
                        entity_name = entity.get('entity_name')
                        if entity_name in retyped:
                            new_type = retyped[entity_name]
                            if new_type and new_type.lower() != 'unknown':
                                entity_updates.append({
                                    'id': entity['id'],
                                    'new_entity_type': new_type.lower()
                                })
                                unknown_retyped += 1
                                logger.debug(f"    Retyped '{entity_name}': UNKNOWN → {new_type}")
                except Exception as e:
                    logger.warning(f"  ⚠️ Failed to retype batch {i//batch_size + 1}: {e}")
            
            if unknown_retyped > 0:
                logger.info(f"  ✅ LLM retyped {unknown_retyped}/{len(unknown_entities)} UNKNOWN entities")
        
        entities_corrected = 0
        if entity_updates:
            logger.info(f"\n💾 Updating {len(entity_updates)} entity types in Neo4j...")
            entities_corrected = neo4j_io.update_entity_types(entity_updates)
        else:
            logger.info("\n✅ No entity type corrections needed (native LightRAG extraction working)")

        phase_times['Phase 2 · Entity Normalization'] = time.time() - phase_start
        logger.info(f"  ⏱️  Phase 2 completed in {phase_times['Phase 2 · Entity Normalization']:.1f}s")
        
        # Phase 3: Generic Relationship Type Resolution (NO LLM)
        # ========================================================================
        # After entity types are corrected (table→requirement, etc.), re-type
        # RELATED_TO relationships using entity-pair lookup. These RELATED_TO rels
        # originate from LLM-produced belongs_to/contained_in/part_of that were
        # normalized to RELATED_TO by schema.normalize_relationship_type().
        # ========================================================================
        phase_start = time.time()
        logger.info("\n🔗 Phase 3 · Relationship Normalization: Resolving generic types (entity-pair lookup)...")

        # Reload entities with corrected types
        entities = neo4j_io.get_all_entities()
        relationships = neo4j_io.get_all_relationships()
        
        # Build entity lookup by elementId
        entity_by_id = {e['id']: e for e in entities}

        retype_updates = collect_relationship_retype_updates(relationships, entity_by_id)
        
        relationships_retyped = 0
        if retype_updates:
            logger.info(f"  Found {len(retype_updates)} generic relationships to retype")
            relationships_retyped = neo4j_io.retype_relationships(retype_updates)
        else:
            logger.info("  ✅ No generic relationships need retyping")
        
        # Refresh grouped entities for algorithm phase
        grouped = group_entities_by_type(entities)
        
        phase_times['Phase 3 · Rel Normalization'] = time.time() - phase_start
        logger.info(f"  ⏱️  Phase 3 completed in {phase_times['Phase 3 · Rel Normalization']:.1f}s")
        
        # Phase 4: Infer missing relationships using PARALLEL modular algorithms
        phase_start = time.time()
        logger.info("\n🔗 Phase 4 · Relationship Inference: Running parallel algorithms...")
        
        # Build lookups for algorithm orchestrator
        entities_by_type = grouped  # Already built from step 2
        id_to_entity = {e['id']: e for e in entities}
        
        new_relationships = await run_all_algorithms_parallel(
            entities=entities,
            entities_by_type=entities_by_type,
            id_to_entity=id_to_entity,
            neo4j_io=neo4j_io,
            model=llm_model_name,
            temperature=temperature,
            existing_relationships=relationships  # Issue #56: Pass for conditional algo execution
        )
        
        relationships_inferred = 0
        if new_relationships:
            logger.info(f"\n💾 Creating {len(new_relationships)} new relationships in Neo4j...")
            relationships_inferred = neo4j_io.create_relationships(new_relationships)
        else:
            logger.info("\n✅ No new relationships inferred")
        
        phase_times['Phase 4 · Rel Inference'] = time.time() - phase_start
        logger.info(f"  ⏱️  Phase 4 completed in {phase_times['Phase 4 · Rel Inference']:.1f}s")

        # Phase 5: Sync inferred relationships to LightRAG VDBs (Issue #65 - Critical Fix)
        # Without this, agent queries via /query miss algorithm-discovered relationships
        phase_start = time.time()
        logger.info("\n🔄 Phase 5 · VDB Synchronization: Syncing inferred relationships...")
        from src.inference.vdb_sync import sync_discoveries_to_vdb
        
        vdb_sync_stats = await sync_discoveries_to_vdb(
            neo4j_io=neo4j_io,
            relationships_inferred=relationships_inferred
        )
        
        relationships_synced = vdb_sync_stats.get("relationships_synced", 0)
        if vdb_sync_stats.get("status") == "success":
            logger.info(f"✅ VDB sync complete: {relationships_synced} relationships now queryable")
        elif vdb_sync_stats.get("status") == "skipped":
            logger.warning(f"⚠️ VDB sync skipped: {vdb_sync_stats.get('reason', 'unknown')}")
        else:
            logger.error(f"❌ VDB sync failed: {vdb_sync_stats.get('error', 'unknown')}")
        
        phase_times['Phase 5 · VDB Sync'] = time.time() - phase_start
        logger.info(f"  ⏱️  Phase 5 completed in {phase_times['Phase 5 · VDB Sync']:.1f}s")

        # Authoritative final counts: capture only after every processing phase,
        # including VDB sync side effects, has finished.
        type_counts = neo4j_io.get_entity_count_by_type()
        rel_counts = neo4j_io.get_relationship_count_by_type()
        result = build_post_processing_result(
            rag_storage_path=rag_storage_path,
            type_counts=type_counts,
            rel_counts=rel_counts,
            entities_corrected=entities_corrected,
            relationships_inferred=relationships_inferred,
            relationships_synced=relationships_synced,
            processing_time=processing_time,
            starting_entity_count=starting_entity_count,
            starting_relationship_count=starting_rel_count,
            vdb_sync_status=vdb_sync_stats.get("status", "unknown"),
        )
        final_entity_count = result["final_entity_count"]
        final_relationship_count = result["final_relationship_count"]
        vdb_entity_count = result["vdb_entity_count"]
        vdb_relationship_count = result["vdb_relationship_count"]
        
        # Summary statistics
        processing_time = time.time() - start_time
        logger.info("\n" + "="*80)
        logger.info("✅ SEMANTIC POST-PROCESSING COMPLETE")
        logger.info("="*80)
        logger.info(f"  Total time:              {processing_time:.1f}s")
        for phase_name, phase_duration in phase_times.items():
            logger.info(f"    {phase_name:30s}  {phase_duration:6.1f}s")
        logger.info(f"  Entities corrected:      {entities_corrected}")
        logger.info(f"  Relationships retyped:   {relationships_retyped}")
        logger.info(f"  Relationships inferred:  {relationships_inferred}")
        logger.info(f"  Relationships synced:    {relationships_synced}")
        logger.info(f"  Processing time:         {processing_time:.2f}s")
        logger.info("="*80)
        
        logger.info("\n📊 Entity Type Distribution (ALL 18 types):")
        # Show all types, sorted by count
        for entity_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  {entity_type:30s}: {count:4d}")

        logger.info("\n📊 Relationship Type Distribution (final Neo4j graph):")
        for relationship_type, count in sorted(rel_counts.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  {relationship_type:30s}: {count:4d}")
        
        # Show summary counts
        logger.info("\n" + "="*60)
        logger.info("📈 FINAL COUNTS (after all processing complete):")
        logger.info("="*60)
        logger.info(f"  Final Neo4j Entities:          {final_entity_count}")
        logger.info(f"  Final Neo4j Relationships:     {final_relationship_count}")
        if vdb_entity_count is not None:
            logger.info(f"  Final VDB Entity Entries:      {vdb_entity_count}")
        if vdb_relationship_count is not None:
            logger.info(f"  Final VDB Relationship Entries: {vdb_relationship_count}")
        logger.info(f"  ─────────────────────────────────────")
        logger.info(f"  Post-Processing Retyped Rels:  {relationships_retyped}")
        logger.info(f"  Post-Processing Added Rels:    {relationships_inferred}")
        logger.info(f"  VDB Synced Relationships:      {relationships_synced}")
        logger.info("="*60)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error during Neo4j post-processing: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "entities_corrected": 0,
            "relationships_inferred": 0,
            "processing_time": time.time() - start_time
        }
    finally:
        neo4j_io.close()


async def enhance_knowledge_graph(
    rag_storage_path: str,
    llm_func: Callable[[str, str], Awaitable[str]],
    batch_size: int = 50
) -> Dict:
    """
    Run semantic post-processing on extracted knowledge graph (Neo4j).
    
    5-phase pipeline:
    1. Data Loading - read entities/relationships from Neo4j
    2. Entity Normalization - fix table/hash types
    3. Relationship Normalization - retype generic RELATED_TO
    4. Relationship Inference - L↔M links, doc structure, orphan resolution
    5. VDB Synchronization - sync inferred rels to vector DB
    
    Args:
        rag_storage_path: Path to rag_storage directory (unused - kept for API compatibility)
        llm_func: Async LLM function (unused - we use centralized call_llm_async)
        batch_size: Batch size for LLM calls (default: 50)
    
    Returns:
        Stats dict with:
        - relationships_inferred: Number of new relationships
        - processing_time: Total time in seconds
    """
    # Get LLM model from centralized settings - use REASONING model for post-processing
    settings = get_settings()
    llm_model = settings.post_processing_llm_name
    llm_temp = settings.llm_model_temperature
    
    # Startup banner with active configuration
    logger.info("")
    logger.info("=" * 80)
    logger.info("🧠 SEMANTIC POST-PROCESSING: 5-Phase Pipeline")
    logger.info("=" * 80)
    logger.info(f"  Post-Processing Model: {llm_model}")
    logger.info(f"  Temperature:           {llm_temp}")
    logger.info(f"  Workspace Path:        {rag_storage_path}")
    logger.info("  Phases: Data Loading → Entity Norm → Rel Norm → Inference → VDB Sync")
    logger.info("=" * 80)
    
    return await _semantic_post_processor_neo4j(
        llm_model_name=llm_model,
        temperature=llm_temp,
        rag_storage_path=rag_storage_path,
    )
