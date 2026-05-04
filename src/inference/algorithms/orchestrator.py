"""
Orchestrator: Parallel Execution of Inference Algorithms

Issue #85: Reduced from 8 algorithms to 3 after data-driven analysis showed
extraction prompt + specialized entity types now cover algorithms 2-6.

Active:
- infer_lm_links: L↔M instruction-eval linking (cross-document gap, only 3 GUIDES from extraction)
- infer_document_structure: Heuristic regex (zero LLM cost, deterministic)
- resolve_orphans: Orphan resolution (13% orphan rate, 86 orphan requirements)
"""
import asyncio
import logging
from typing import Dict, List

from src.core import get_settings
from .orchestrator_support import AlgorithmRunSpec, collect_algorithm_relationships
from .infer_lm_links import infer_lm_links
from .infer_document_structure import infer_document_structure
from .resolve_orphans import resolve_orphans
from .base import load_prompt_template

logger = logging.getLogger(__name__)

_settings = get_settings()
MAX_CONCURRENT_LLM_CALLS = _settings.get_effective_post_processing_max_async()


async def run_all_algorithms_parallel(
    entities: List[Dict],
    entities_by_type: Dict,
    id_to_entity: Dict,
    neo4j_io,
    model: str,
    temperature: float,
    existing_relationships: List[Dict] = None
) -> List[Dict]:
    """
    Execute inference algorithms in parallel via asyncio.gather.
    
    Architecture:
    - LLM-powered (infer_lm_links, resolve_orphans): run in parallel with semaphore
    - Heuristic (infer_document_structure): instant regex, runs after LLM phase
    
    Args:
        entities: All entities to analyze
        entities_by_type: Entities grouped by type
        id_to_entity: Entity ID → entity dict mapping
        neo4j_io: Neo4jGraphIO instance for querying
        model: LLM model name
        temperature: LLM temperature
        existing_relationships: Relationships from extraction (unused, kept for API compat)
        
    Returns:
        Combined list of all inferred relationships
    """
    logger.info(f"\n⚡ Starting parallel inference (MAX_ASYNC={MAX_CONCURRENT_LLM_CALLS})")
    
    # Load shared system prompt once
    system_prompt = await load_prompt_template("system_prompt.md")
    
    # =========================================================================
    # LLM-powered algorithms (parallel)
    # =========================================================================
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
    
    async def rate_limited(coro):
        async with semaphore:
            return await coro
    
    tasks = [
        rate_limited(infer_lm_links(
            entities_by_type, id_to_entity, system_prompt, model, temperature
        )),
        rate_limited(resolve_orphans(
            entities, id_to_entity, neo4j_io, model, temperature, system_prompt
        )),
    ]
    
    algorithm_names = [
        "L↔M Links",
        "Orphan Resolution",
    ]
    
    logger.info(f"  Running {len(tasks)} LLM-powered algorithms...")
    results = await asyncio.gather(*tasks, return_exceptions=True)

    algorithm_runs = [
        AlgorithmRunSpec(name=name, result=result)
        for name, result in zip(algorithm_names, results)
    ]
    all_relationships = collect_algorithm_relationships(algorithm_runs, logger=logger)
    
    # =========================================================================
    # Heuristic algorithm (instant, no LLM)
    # =========================================================================
    
    logger.info("\n  Running document structure heuristic...")
    heuristic_rels = infer_document_structure(entities, entities_by_type)
    all_relationships.extend(heuristic_rels)
    logger.info(f"  ✅ Doc Structure: {len(heuristic_rels)} relationships")
    
    # =========================================================================
    # Summary
    # =========================================================================
    
    logger.info(f"\n✅ Total inferred relationships: {len(all_relationships)}")
    
    return all_relationships

