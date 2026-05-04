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
import os
import re
import asyncio
from typing import Dict, Callable, Awaitable, List
from pydantic import ValidationError

from src.core import get_settings
from src.inference.neo4j_graph_io import Neo4jGraphIO, group_entities_by_type
from src.inference.algorithms import run_all_algorithms_parallel
from src.inference.semantic_post_process_support import (
    GENERIC_REL_TYPES as _GENERIC_REL_TYPES,
    build_post_processing_result,
    collect_relationship_retype_updates,
    count_vdb_entries as _count_vdb_entries,
    heuristic_table_type_mapping as _heuristic_table_type_mapping,
    resolve_generic_relationship as _resolve_generic_relationship,
)
from src.ontology.schema import VALID_ENTITY_TYPES, InferredRelationship
from src.utils.llm_client import call_llm_async
from src.utils.llm_parsing import extract_json_from_response, parse_with_pydantic

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


async def _parse_and_validate_relationship_batch(
    response: str,
    id_to_entity: Dict,
    context: str
) -> List[Dict]:
    """
    Parse LLM response and validate relationships with Pydantic (Branch 040 pattern).
    
    Shared helper for all relationship inference algorithms.
    Validates relationships ONE-BY-ONE to gracefully filter self-loops and bad data.
    
    Args:
        response: Raw LLM response text
        id_to_entity: Dict mapping entity IDs to entity objects
        context: Context string for logging (e.g., "L↔M Links Batch 2")
        
    Returns:
        List of valid relationship dicts ready for Neo4j insertion
    """
    try:
        # Step 1: Extract JSON from response (handles markdown code blocks, etc.)
        response_json = extract_json_from_response(response, allow_array=True)
        
        # Step 2: Normalize to list of relationship dicts
        if isinstance(response_json, dict):
            # Handle {"relationships": [...]} or {"results": [...]} format
            relationships_data = response_json.get('relationships') or response_json.get('results') or []
        elif isinstance(response_json, list):
            relationships_data = response_json
        else:
            logger.warning(f"    ⚠️ {context}: Unexpected JSON type {type(response_json)}")
            return []
        
        # Step 3: Validate relationships ONE-BY-ONE (graceful partial validation)
        valid_rels = []
        filtered_count = 0
        self_loop_count = 0
        hallucination_count = 0
        
        for idx, rel_data in enumerate(relationships_data):
            try:
                # Validate with Pydantic (catches self-loops, normalizes fields)
                rel = InferredRelationship.model_validate(rel_data)
                
                # Verify entity IDs exist in graph
                if rel.source_id not in id_to_entity:
                    logger.debug(f"    {context}: Unknown source_id '{rel.source_id}'")
                    hallucination_count += 1
                    continue
                if rel.target_id not in id_to_entity:
                    logger.debug(f"    {context}: Unknown target_id '{rel.target_id}'")
                    hallucination_count += 1
                    continue
                
                # Convert to dict for Neo4j insertion
                valid_rels.append(rel.to_dict())
                
            except ValidationError as ve:
                # Pydantic caught a validation error (self-loop, missing field, etc.)
                filtered_count += 1
                if 'Self-loop' in str(ve):
                    self_loop_count += 1
                logger.debug(f"    {context}: Validation error for relationship {idx}: {ve}")
                continue
            except Exception as e:
                filtered_count += 1
                logger.debug(f"    {context}: Unexpected error for relationship {idx}: {e}")
                continue
        
        # Log summary
        total = len(relationships_data)
        if filtered_count > 0 or hallucination_count > 0:
            logger.info(f"    {context}: {len(valid_rels)}/{total} valid "
                       f"(filtered: {filtered_count}, hallucinated: {hallucination_count}, self-loops: {self_loop_count})")
        
        return valid_rels
        
    except Exception as e:
        logger.error(f"    ❌ {context}: Failed to parse response: {e}")
        return []


async def _infer_relationships_batch(entities: List[Dict], existing_rels: List[Dict], model: str, temperature: float) -> List[Dict]:
    """
    Infer missing relationships between entities using chunked batching with ID-based lookups.
    
    With 2M context window, processes 500 entities per batch with 100-entity overlap.
    This reduces LLM calls by 90%+ while maintaining cross-batch relationship detection.
    
    **ID-Based Approach (Branch 013a):**
    - LLM receives entity IDs (e.g., "entity_123") instead of names
    - Eliminates ambiguity from name mismatches (e.g., "Subfactor 1.1: TOMP" vs "TOMP")
    - 100% match rate for valid relationships
    
    Args:
        entities: All entities to analyze
        existing_rels: Existing relationships (for context)
        model: LLM model name
        temperature: LLM temperature
        
    Returns:
        List of inferred relationships
    """
    import json
    
    all_relationships = []
    batch_size = 500  # Increased from 50 to leverage 2M context window
    overlap = 100     # Increased from 25 to maintain relationship coverage
    total_entities = len(entities)
    
    # Build ID-to-entity mapping and entity reference list for LLM
    id_to_entity = {e['id']: e for e in entities}
    
    # Process in overlapping batches
    batch_num = 0
    start_idx = 0
    
    while start_idx < total_entities:
        end_idx = min(start_idx + batch_size, total_entities)
        batch_entities = entities[start_idx:end_idx]
        batch_num += 1
        
        logger.info(f"  Processing batch {batch_num}: entities {start_idx+1}-{end_idx} of {total_entities}")
        
        # Build entity reference table with IDs (eliminates name ambiguity)
        # Format: entity_123 | requirement | Task Order Management Plan (TOMP) | Contractor shall develop...
        entity_table = "ID | Type | Name | Description\n" + ("-" * 80) + "\n"
        entity_table += "\n".join([
            f"{e['id']} | {e['entity_type']} | {e['entity_name']} | {e.get('description', '')[:5000]}"
            for e in batch_entities
        ])
        
        prompt = f"""You are analyzing a government contracting knowledge graph. Identify missing relationships between these entities.

ENTITY REFERENCE TABLE:
{entity_table}

Relationship types to use:

REQUIREMENT-CENTRIC:
- REQUIRES: Requirement → Equipment/Resource needed (including quantified items)
- ENABLED_BY: Requirement → Government-provided Technology/Equipment
- FULFILLS: Deliverable → Requirement it satisfies
- RESPONSIBLE_FOR: Person → Deliverable they submit/create

STRUCTURAL:
- PART_OF: Sub-component → Parent component
- FIELD_IN: Table field → Table/Document containing it
- REFERENCES: Document/Document Section → Another document/section

REGULATORY:
- EVALUATES: Evaluation criteria → proposal instructions and requirements
- APPLIES_TO: Clause/Regulation → Program/Contract

SPECIAL PATTERNS TO CATCH:
1. Quantified equipment: "X receptacles must be emptied Y times" → REQUIRES(requirement → equipment)
2. Government-provided: "furnished by Government" → ENABLED_BY(requirement → technology)
3. Conditional equipment: "may substitute" → REQUIRES(requirement → equipment)
4. Table fields: "field in X table" → FIELD_IN(concept → document)
5. Person submissions: "shall submit" → RESPONSIBLE_FOR(person → deliverable)

Find logical relationships that are missing. For each relationship, provide:
1. Source entity ID (from ID column above - e.g., "4:abc123...")
2. Target entity ID (from ID column above - e.g., "4:def456...")
3. Relationship type (one of the above)
4. Confidence (0.0-1.0)
5. Brief reasoning

**CRITICAL**: Use entity IDs from the table above, NOT entity names. IDs eliminate ambiguity.

Format your response as JSON array:
[
  {{"source_id": "4:abc123...", "target_id": "4:def456...", "type": "EVALUATES", "confidence": 0.85, "reasoning": "..."}}
]

Return ONLY the JSON array. If no relationships found, return []."""
        
        try:
            response = await call_llm_async(prompt, model=model, temperature=temperature)
            
            # Parse JSON response
            relationships = json.loads(response)
            
            # Validate entity IDs and build relationships
            for rel in relationships:
                # Handle both 'type' and 'relationship_type' keys
                rel_type = rel.get('type') or rel.get('relationship_type')
                if not rel_type:
                    logger.warning(f"  Skipping relationship without type: {rel}")
                    continue
                
                source_id = rel.get('source_id')
                target_id = rel.get('target_id')
                
                # Validate IDs exist in our entity map
                if source_id in id_to_entity and target_id in id_to_entity:
                    all_relationships.append({
                        'source_id': source_id,
                        'target_id': target_id,
                        'relationship_type': rel_type,
                        'confidence': rel.get('confidence', 0.7),
                        'reasoning': rel.get('reasoning', '')
                    })
                else:
                    if source_id not in id_to_entity:
                        logger.warning(f"  Invalid source entity ID: {source_id}")
                    if target_id not in id_to_entity:
                        logger.warning(f"  Invalid target entity ID: {target_id}")
            
            logger.info(f"    → Found {len(relationships)} relationships in batch {batch_num}")
            
        except json.JSONDecodeError as e:
            logger.error(f"  JSON parse error in batch {batch_num}: {e}")
        except Exception as e:
            logger.error(f"  Error inferring relationships in batch {batch_num}: {e}", exc_info=True)
        
        # Move to next batch with overlap
        start_idx += (batch_size - overlap)
    
    logger.info(f"\n  Total relationships inferred across {batch_num} batches: {len(all_relationships)}")
    return all_relationships


async def _load_prompt_template(prompt_filename: str) -> str:
    """Load a prompt template from prompts/relationship_inference/"""
    from pathlib import Path
    prompt_path = Path("prompts/relationship_inference") / prompt_filename
    try:
        return prompt_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        logger.error(f"Prompt template not found: {prompt_path}")
        return ""


def _validate_relationships(rels: List[Dict], id_to_entity: Dict, algorithm_name: str) -> List[Dict]:
    """
    Validate relationships using Pydantic models (Branch 040 pattern).
    
    Graceful degradation: Validates ONE-BY-ONE, drops bad ones, keeps batch.
    
    Args:
        rels: List of relationship dicts from LLM
        id_to_entity: Mapping of entity IDs to entities
        algorithm_name: Name of algorithm for logging
        
    Returns:
        List of valid relationships with required fields only
    """
    valid_rels = []
    filtered_count = 0
    self_loop_count = 0
    hallucination_count = 0
    
    for rel in rels:
        try:
            # Validate with Pydantic (catches self-loops, normalizes fields)
            validated = InferredRelationship.model_validate(rel)
            
            # Verify entity IDs exist in graph
            if validated.source_id not in id_to_entity:
                hallucination_count += 1
                continue
            if validated.target_id not in id_to_entity:
                hallucination_count += 1
                continue
            
            # Convert to dict for Neo4j insertion
            valid_rels.append(validated.to_dict())
            
        except ValidationError as ve:
            # Pydantic caught a validation error (self-loop, missing field, etc.)
            filtered_count += 1
            if 'Self-loop' in str(ve):
                self_loop_count += 1
            logger.debug(f"    {algorithm_name}: Pydantic validation failed - {ve}")
            continue
        except Exception as e:
            filtered_count += 1
            logger.debug(f"    {algorithm_name}: Unexpected error - {e}")
            continue
    
    # Log summary if any were filtered
    total = len(rels)
    if filtered_count > 0 or hallucination_count > 0:
        logger.info(f"    {algorithm_name}: {len(valid_rels)}/{total} valid "
                   f"(filtered: {filtered_count}, hallucinated: {hallucination_count}, self-loops: {self_loop_count})")
    
    return valid_rels


async def _resolve_orphan_patterns(
    entities: List[Dict],
    id_to_entity: Dict[str, Dict],
    neo4j_io,
    model: str,
    temperature: float
) -> List[Dict]:
    """
    Resolve orphaned entities using LLM-powered relationship inference.
    
    Strategy: Single batched LLM call with all orphans + connected entities
    for focused inference. More efficient than per-orphan calls and more
    adaptive than regex patterns.
    
    Patterns addressed:
    - Equipment/Technology → Requirements (quantified, Gov't-provided)
    - Person → Deliverable (submission responsibilities)
    - Concept → Document (table fields, data elements)
    - Any other missing relationships the LLM detects
    
    Args:
        entities: All entities to analyze
        id_to_entity: Entity ID lookup dictionary
        neo4j_io: Neo4jGraphIO instance for querying orphans
        model: LLM model name
        temperature: LLM temperature
        
    Returns:
        List of relationships for orphan patterns
    """
    import json
    
    # Get truly orphaned entity IDs from Neo4j (nodes with NO relationships)
    orphan_ids = set(neo4j_io.get_orphaned_entity_ids())
    
    if not orphan_ids:
        logger.info("    → No orphaned entities found")
        return []
    
    # Filter entities to only those that are actually orphaned
    orphaned = [e for e in entities if e['id'] in orphan_ids]
    
    if not orphaned:
        logger.info("    → No orphaned entities found")
        return []
    
    logger.info(f"    → Found {len(orphaned)} orphaned entities")
    
    # Build entity type indices for candidate relationships
    entities_by_type = {}
    for e in entities:
        etype = e.get('entity_type', 'concept')
        if etype not in entities_by_type:
            entities_by_type[etype] = []
        entities_by_type[etype].append(e)
    
    # Gather candidate entities for linking (focus on high-value types)
    candidate_types = ['requirement', 'deliverable', 'document', 'clause', 'document_section',
                      'work_scope_item', 'evaluation_factor', 'proposal_instruction', 'technology', 'equipment']
    
    candidates = []
    for etype in candidate_types:
        candidates.extend(entities_by_type.get(etype, []))
    
    # Limit candidates to avoid massive prompts (take top 200 most relevant)
    # Prioritize requirements and deliverables (most common link targets)
    priority_candidates = (
        entities_by_type.get('requirement', [])[:100] +
        entities_by_type.get('deliverable', [])[:50] +
        entities_by_type.get('document', [])[:30] +
        entities_by_type.get('clause', [])[:20]
    )
    
    if not priority_candidates:
        logger.info("    → No candidate entities for linking")
        return []
    
    logger.info(f"    → Using {len(orphaned)} orphans × {len(priority_candidates)} candidates for inference")
    
    # Build JSON representations (truncate descriptions to save tokens)
    orphan_json = json.dumps([{
        'id': o['id'],
        'name': o['entity_name'],
        'type': o.get('entity_type'),
        'description': o.get('description', '')[:5000]
    } for o in orphaned], indent=2)
    
    candidate_json = json.dumps([{
        'id': c['id'],
        'name': c['entity_name'],
        'type': c.get('entity_type'),
        'description': c.get('description', '')[:5000]
    } for c in priority_candidates], indent=2)
    
    # LLM prompt optimized for orphan resolution
    prompt = f"""You are analyzing orphaned entities in a government contracting knowledge graph. 
These entities were extracted correctly but lack relationships to other entities.

ORPHANED ENTITIES (need relationships):
{orphan_json}

CANDIDATE ENTITIES (potential relationship targets):
{candidate_json}

Find logical relationships for as many orphans as possible. Common patterns:

REQUIREMENT-CENTRIC:
- REQUIRES: Requirement → Equipment/Resource (e.g., "Trash must be emptied" → trash receptacles)
- ENABLED_BY: Requirement → Gov't-provided Technology/Equipment (e.g., "GFE ancillary hardware")
- SATISFIED_BY: Requirement → Deliverable

PERSON-CENTRIC:
- RESPONSIBLE_FOR: Person → Deliverable they submit/create (e.g., "Program Manager submits QCP")

DOCUMENT-CENTRIC:
- FIELD_IN: Table field/Data element → Document/Clause containing it (e.g., "DODAAC field in WAWF table")
- PART_OF: Sub-component → Parent document
- REFERENCES: Document → Another document

SPECIAL PATTERNS:
- Quantified items: "X equipment must be Y times" → REQUIRES
- Government-provided: "furnished by Government" → ENABLED_BY
- Conditional requirements: "may substitute" → REQUIRES
- Table/data references: "field in X" → FIELD_IN

Use entity IDs from 'id' field. Return ONLY valid relationships.
Return ONLY valid JSON array:
[
  {{"source_id": "entity_id", "target_id": "entity_id", "relationship_type": "TYPE", "reasoning": "brief evidence"}}
]

If no relationships found, return []."""

    try:
        response = await call_llm_async(prompt, model=model, temperature=temperature)
        rels = json.loads(response.strip())
        valid_rels = _validate_relationships(rels, id_to_entity, "Orphan Resolution")
        logger.info(f"    → Found {len(valid_rels)} orphan relationships")
        return valid_rels
    except Exception as e:
        logger.error(f"    ❌ Orphan resolution failed: {e}")
        return []


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
