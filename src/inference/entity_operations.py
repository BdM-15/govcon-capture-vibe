"""
Entity Type Correction - Semantic Post-Processing Operation
============================================================

Purpose: Eliminate UNKNOWN/forbidden entity types using LLM retyping
Context: LLM extraction may produce non-standard entity types
Solution: Post-process extracted entities with strict type enforcement

Architecture (Issue #54 - Back to Basics):
- Runs BEFORE relationship inference (clean entities → better relationships)
- Uses unified BatchProcessor for efficient batching
- Simple prompt: "Retype these entities using ONLY these 18 govcon types"
- Cost: ~$0.005-0.01 per RFP (200 entities × 100 tokens = ~20K tokens)
- Note: Native LightRAG extraction reduces need for type correction

Integration: Called from semantic_post_processor.enhance_knowledge_graph()
"""

import logging
from typing import List, Dict, Tuple, Callable, Awaitable

from src.inference.batch_processor import BatchProcessor
from src.inference.entity_type_support import (
    ALLOWED_TYPES,
    FORBIDDEN_TYPES,
    count_types,
    create_retyping_prompt,
    identify_forbidden_entities,
    validate_no_forbidden_types,
)

logger = logging.getLogger(__name__)


async def retype_entities_batch(
    entities_batch: List[Dict],
    llm_func: Callable[[str, str], Awaitable[str]],
) -> Dict[str, str]:
    """
    Retype a batch of entities using LLM.
    
    Args:
        entities_batch: List of entities to retype
        llm_func: LLM function (async) that takes (prompt, system_prompt) and returns response
    
    Returns:
        Dict mapping entity_name → new_entity_type
    """
    if not entities_batch:
        return {}
    
    prompt = create_retyping_prompt(entities_batch)
    system_prompt = "You are an expert entity type classifier for government contracting documents. Output ONLY entity types, one per line, using the exact allowed types provided."
    
    try:
        response = await llm_func(prompt, system_prompt)
        
        # Parse response: expect numbered lines like "1. concept"
        lines = response.strip().split("\n")
        retyped = {}
        
        for i, line in enumerate(lines):
            if i >= len(entities_batch):
                break  # More responses than entities (shouldn't happen)
            
            # Extract type from line (handle "1. concept" or just "concept")
            line = line.strip()
            if ". " in line:
                line = line.split(". ", 1)[1]
            
            entity_type = line.strip().lower()
            
            # Validate it's an allowed type
            if entity_type in ALLOWED_TYPES:
                entity_name = entities_batch[i].get("entity_name")
                retyped[entity_name] = entity_type
            else:
                # LLM output invalid type - fallback to concept
                entity_name = entities_batch[i].get("entity_name")
                retyped[entity_name] = "concept"
                logger.warning(f"LLM returned invalid type '{entity_type}' for '{entity_name}', using 'concept'")
        
        return retyped
    
    except Exception as e:
        logger.error(f"Failed to retype entities batch: {e}")
        # Fallback: retype all to 'concept'
        return {entity.get("entity_name"): "concept" for entity in entities_batch}


async def correct_entity_types(
    entities: List[Dict],
    llm_func: Callable[[str, str], Awaitable[str]],
    batch_size: int = 50,
) -> Tuple[List[Dict], Dict[str, str]]:
    """
    Main entity type correction operation using unified BatchProcessor.
    
    Identifies entities with forbidden types and retypes them using LLM.
    Uses the centralized batching infrastructure for consistent processing.
    
    Args:
        entities: List of all entities from GraphML
        llm_func: LLM function for retyping
        batch_size: Number of entities to process per LLM call (default: 50)
    
    Returns:
        Tuple of (updated_entities_list, retyping_map)
        - updated_entities_list: All entities with forbidden types fixed
        - retyping_map: Dict of entity_name → new_type (for logging)
    """
    logger.info("🔧 Entity Type Correction Operation")
    
    # Identify entities with forbidden types
    forbidden = identify_forbidden_entities(entities, logger=logger)
    
    if not forbidden:
        logger.info("✅ No forbidden types found - correction not needed")
        return entities, {}
    
    # Use unified BatchProcessor for retyping
    processor = BatchProcessor(batch_size=batch_size)
    
    # Define batch processing function
    async def process_batch(batch: List[Dict]) -> Dict[str, str]:
        return await retype_entities_batch(batch, llm_func)
    
    # Process all forbidden entities in batches
    all_retypings = await processor.process_batches(
        items=forbidden,
        process_fn=process_batch,
        batch_name="Entity Type Correction",
        aggregate_fn=processor.merge_dict_results
    )
    
    # Apply retypings to entities list
    updated_count = 0
    for entity in entities:
        entity_name = entity.get("entity_name")
        if entity_name in all_retypings:
            old_type = entity.get("entity_type")
            new_type = all_retypings[entity_name]
            entity["entity_type"] = new_type
            updated_count += 1
            logger.debug(f"Retyped: '{entity_name}' from '{old_type}' → '{new_type}'")
    
    logger.info(f"✅ Entity Type Correction complete: {updated_count} entities retyped")
    logger.info(f"   Type distribution: {count_types(all_retypings)}")
    
    return entities, all_retypings

