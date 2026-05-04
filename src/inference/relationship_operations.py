"""
Relationship Inference - Semantic Post-Processing Operation
============================================================

Purpose: Discover missing relationships between entities using LLM semantic understanding
Context: Multimodal extraction captures entities but misses many cross-references
Solution: Post-process extracted entities with 7 relationship inference algorithms

Architecture:
- Runs AFTER entity type correction (clean entities → better relationship detection)
- Uses unified BatchProcessor for efficient batching
- 7 algorithms: 5 LLM-powered + 2 heuristic
- Cost: ~$0.03 per RFP (5 LLM batches × ~$0.006/batch)

Integration: Called from semantic_post_processor.enhance_knowledge_graph()
"""

import logging
from typing import List, Dict, Tuple, Callable, Awaitable
from src.utils.logging_config import log_graceful_failure
from src.utils.llm_parsing import extract_json_from_response

from src.inference.batch_processor import BatchProcessor
from src.inference.neo4j_graph_io import group_entities_by_type
from src.inference.relationship_inference_support import (
    apply_canonical_mapping,
    apply_type_based_heuristics,
    build_deduplication_prompt,
    collect_existing_pairs,
    find_entity_id,
    find_potential_duplicate_pairs,
)
from src.core.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


async def deduplicate_entities(
    nodes: List[Dict],
    edges: List[Dict],
    llm_func: Callable
) -> Tuple[List[Dict], List[Dict], Dict[str, str]]:
    """
    Use LLM to identify and merge duplicate entities caused by formatting variations.
    
    Government RFPs use inconsistent formatting for the same entity:
    - "SECTION C.4 - SUPPLY" vs "Section C.4" vs "section c.4"
    - "FAR 52.212-1" vs "far 52.212-1" vs "FAR clause 52.212-1"
    
    This function uses semantic understanding to detect duplicates and create canonical names.
    
    Args:
        nodes: List of entity nodes
        edges: List of relationships
        llm_func: Async LLM function for deduplication
        
    Returns:
        Tuple of (deduplicated_nodes, updated_edges, canonical_mapping)
        where canonical_mapping is {old_name: canonical_name}
    """
    # Group entities by type for efficient comparison
    grouped = group_entities_by_type(nodes)

    canonical_mapping = {}  # old_name -> canonical_name

    for entity_type, potential_duplicates in find_potential_duplicate_pairs(grouped).items():
        if potential_duplicates:
            logger.info(f"    Found {len(potential_duplicates)} potential {entity_type} duplicates to verify...")

            for i in range(0, len(potential_duplicates), 10):
                batch = potential_duplicates[i:i+10]
                prompt = build_deduplication_prompt(batch)

                try:
                    response = await llm_func(prompt, "You are an expert at identifying duplicate entities in government RFP documents.")
                    result = extract_json_from_response(response)

                    for dup_group in result.get('duplicates', []):
                        canonical = dup_group.get('canonical_name')
                        duplicates = dup_group.get('duplicates', [])

                        for dup_name in duplicates:
                            canonical_mapping[dup_name] = canonical

                except Exception as e:
                    logger.warning(f"Failed to process deduplication batch: {e}")
                    continue
    
    # If no duplicates found, return original data
    if not canonical_mapping:
        return nodes, edges, {}

    deduplicated_nodes, updated_edges = apply_canonical_mapping(nodes, edges, canonical_mapping)
    return deduplicated_nodes, updated_edges, canonical_mapping


async def infer_relationships_batch(
    source_entities: List[Dict],
    target_entities: List[Dict],
    relationship_context: str,
    llm_func: Callable
) -> List[Dict]:
    """
    Infer relationships between source and target entities using LLM.
    
    Args:
        source_entities: List of source entity dicts
        target_entities: List of target entity dicts
        relationship_context: Prompt template with relationship rules
        llm_func: Async LLM function for inference
        
    Returns:
        List of relationship dicts
    """
    if not source_entities or not target_entities:
        return []
    
    # Build entity context for prompt
    source_context = "\n".join([
        f"- {e.get('entity_name')} (type: {e.get('entity_type')}): {e.get('description', '')[:100]}..."
        for e in source_entities[:20]  # Limit to first 20 to avoid token limits
    ])
    
    target_context = "\n".join([
        f"- {e.get('entity_name')} (type: {e.get('entity_type')}): {e.get('description', '')[:100]}..."
        for e in target_entities[:20]
    ])
    
    prompt = relationship_context.format(
        source_entities=source_context,
        target_entities=target_context
    )
    
    system_prompt = "You are an expert at analyzing government RFP documents and inferring relationships between entities."
    
    try:
        response = await llm_func(prompt, system_prompt)
        
        # Parse JSON response
        result = extract_json_from_response(response)
        relationships = result.get('relationships', [])
        
        # Convert to internal relationship format
        new_relationships = []
        for rel in relationships:
            new_relationships.append({
                'source_id': find_entity_id(rel.get('source'), source_entities),
                'target_id': find_entity_id(rel.get('target'), target_entities),
                'relationship_type': rel.get('type', 'RELATED_TO'),
                'confidence': rel.get('confidence', 0.7),
                'reasoning': rel.get('reasoning', '')
            })
        
        return new_relationships
    
    except Exception as e:
        log_graceful_failure(logger, "Relationship inference", e)
        return []



async def infer_relationships(
    entities: List[Dict],
    existing_relationships: List[Dict],
    llm_func: Callable,
    batch_size: int = 50
) -> List[Dict]:
    """
    Main relationship inference operation using unified BatchProcessor.
    
    Implements 7 core relationship inference algorithms:
    0. Entity Deduplication (LLM-powered formatting normalization)
    1. Document hierarchy: CHILD_OF relationships (documents → sections)
    2. Clause clustering: CHILD_OF relationships (clauses → sections)
    3. Section L↔M mapping: GUIDES relationships (instructions ↔ factors)
    4. Requirement evaluation: EVALUATED_BY relationships (requirements → factors)
    5. Work-deliverable linking: PRODUCES relationships (SOW → deliverables)
    6. Type-based heuristics: Deterministic UCF patterns
    
    Args:
        entities: List of entity nodes from GraphML
        existing_relationships: List of existing relationships
        llm_func: Async LLM function for inference
        batch_size: Number of items to process per LLM call (default: 50)
        
    Returns:
        List of new relationship dicts
    """
    logger.info("🔗 Relationship Inference Operation")
    logger.info("=" * 80)
    
    # Group entities by type BEFORE deduplication
    grouped = group_entities_by_type(entities)
    
    logger.info(f"  📊 Entity type distribution (before deduplication):")
    for entity_type, entity_list in sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True):
        logger.info(f"    {entity_type}: {len(entity_list)}")
    
    # Algorithm 0: Entity Deduplication & Normalization (runs first!)
    logger.info(f"\n  [0/7] Entity Deduplication: LLM-powered formatting normalization...")
    entities, existing_relationships, canonical_mapping = await deduplicate_entities(
        entities, existing_relationships, llm_func
    )
    
    if canonical_mapping:
        logger.info(f"    ✅ Merged {len(canonical_mapping)} duplicate entities")
        for old_name, new_name in list(canonical_mapping.items())[:5]:
            logger.info(f"      • '{old_name}' → '{new_name}'")
        if len(canonical_mapping) > 5:
            logger.info(f"      ... and {len(canonical_mapping) - 5} more")
    else:
        logger.info(f"    ✅ No duplicates found - entity naming is clean")
    
    # Re-group entities after deduplication
    grouped = group_entities_by_type(entities)
    
    logger.info(f"\n  📊 Entity type distribution (after deduplication):")
    for entity_type, entity_list in sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True):
        logger.info(f"    {entity_type}: {len(entity_list)}")
    
    # Track all inferred relationships
    all_new_relationships = []
    
    # Create unified BatchProcessor
    processor = BatchProcessor(batch_size=batch_size)
    
    # Create set of existing relationships for deduplication
    existing_pairs = collect_existing_pairs(existing_relationships)
    logger.info(f"  Existing relationships: {len(existing_pairs) // 2}")
    
    # Algorithm 1: DOCUMENT → SECTION (Document Hierarchy)
    if 'document' in grouped and 'section' in grouped:
        logger.info(f"\n  [1/7] Document Hierarchy: DOCUMENT → SECTION...")
        relationship_context = load_prompt("relationship_inference/document_section_linking")
        document_section_rels = await infer_relationships_batch(
            source_entities=grouped['document'],
            target_entities=grouped['section'],
            relationship_context=relationship_context,
            llm_func=llm_func
        )
        all_new_relationships.extend(document_section_rels)
    
    # Algorithm 2: CLAUSE → SECTION (Clause Clustering)
    if 'clause' in grouped and 'section' in grouped:
        logger.info(f"\n  [2/7] Clause Clustering: CLAUSE → SECTION...")
        relationship_context = load_prompt("relationship_inference/clause_clustering")
        clause_section_rels = await infer_relationships_batch(
            source_entities=grouped['clause'],
            target_entities=grouped['section'],
            relationship_context=relationship_context,
            llm_func=llm_func
        )
        all_new_relationships.extend(clause_section_rels)
    
    # Algorithm 3: SUBMISSION_INSTRUCTION ↔ EVALUATION_FACTOR (Instruction-Evaluation Linking)
    if 'submission_instruction' in grouped and 'evaluation_factor' in grouped:
        logger.info(f"\n  [3/7] Instruction-Evaluation Linking: SUBMISSION_INSTRUCTION ↔ EVALUATION_FACTOR...")
        relationship_context = load_prompt("relationship_inference/instruction_evaluation_linking")
        instruction_factor_rels = await infer_relationships_batch(
            source_entities=grouped['submission_instruction'],
            target_entities=grouped['evaluation_factor'],
            relationship_context=relationship_context,
            llm_func=llm_func
        )
        all_new_relationships.extend(instruction_factor_rels)
    
    # Algorithm 4: REQUIREMENT → EVALUATION_FACTOR (Requirement Evaluation) - WITH BATCHING
    if 'requirement' in grouped and 'evaluation_factor' in grouped:
        logger.info(f"\n  [4/7] Requirement Evaluation: REQUIREMENT → EVALUATION_FACTOR...")
        relationship_context = load_prompt("relationship_inference/requirement_evaluation")
        
        requirements = grouped['requirement']
        evaluation_factors = grouped['evaluation_factor']
        
        # Use BatchProcessor for large requirement sets
        async def process_requirement_batch(batch: List[Dict]) -> List[Dict]:
            return await infer_relationships_batch(
                source_entities=batch,
                target_entities=evaluation_factors,
                relationship_context=relationship_context,
                llm_func=llm_func
            )
        
        requirement_factor_rels = await processor.process_batches(
            items=requirements,
            process_fn=process_requirement_batch,
            batch_name="Requirement→Factor Inference",
            aggregate_fn=processor.flatten_list_results
        )
        
        all_new_relationships.extend(requirement_factor_rels)
    
    # Algorithm 5: STATEMENT_OF_WORK → DELIVERABLE (Work to Deliverables)
    if 'statement_of_work' in grouped and 'deliverable' in grouped:
        logger.info(f"\n  [5/7] Work to Deliverables: STATEMENT_OF_WORK → DELIVERABLE...")
        relationship_context = load_prompt("relationship_inference/sow_deliverable_linking")
        sow_deliverable_rels = await infer_relationships_batch(
            source_entities=grouped['statement_of_work'],
            target_entities=grouped['deliverable'],
            relationship_context=relationship_context,
            llm_func=llm_func
        )
        all_new_relationships.extend(sow_deliverable_rels)
    
    # Algorithm 6: Type-Based Heuristics (Deterministic UCF Patterns)
    logger.info(f"\n  [6/7] Type-Based Heuristics: Domain-Specific Patterns...")
    heuristic_rels = apply_type_based_heuristics(grouped, existing_relationships)
    all_new_relationships.extend(heuristic_rels)
    logger.info(f"    ✅ Added {len(heuristic_rels)} deterministic relationships")
    
    logger.info(f"\n  🎯 Total relationships inferred: {len(all_new_relationships)}")
    logger.info("=" * 80)
    
    return all_new_relationships
