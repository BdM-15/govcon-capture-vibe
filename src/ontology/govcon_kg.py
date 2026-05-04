"""
GovCon Domain Ontology KG Consolidator

This module consolidates all modular knowledge files into a single
`custom_kg` dictionary compatible with LightRAG's `insert_custom_kg()`.

Architecture Explanation:
-------------------------
We use a MODULAR design where each knowledge domain is a separate Python file:

  src/ontology/knowledge/
    ├── shipley.py         # Shipley BD Lifecycle, Color Teams
    ├── regulations.py     # FAR/DFARS compliance patterns
    ├── evaluation.py      # Rating scales, evaluation factors
    ├── workload.py        # BOE formulas, staffing ratios
    ├── capture.py         # Bid/No-Bid, Win Themes, Discriminators
    ├── lessons_learned.py # 20+ years domain expertise
    └── company_capabilities.py # Company-specific platforms, past performance, discriminators

Each module exports three lists:
  - ENTITIES: List of entity dicts with entity_name, entity_type, description
  - RELATIONSHIPS: List of relationship dicts with src_id, tgt_id, description
  - CHUNKS: List of chunk dicts with content for vector DB

This consolidator:
  1. Imports all modules via __init__.py
  2. Merges all ENTITIES, RELATIONSHIPS, CHUNKS into combined lists
  3. Transforms combined lists into LightRAG's custom_kg format:
     {
       "entities": [
         {"entity_name": ..., "entity_type": ..., "description": ...}
       ],
       "relationships": [
         {"src_id": ..., "tgt_id": ..., "description": ..., "keywords": ..., "weight": ...}
       ],
       "chunks": [
         {"content": ..., "source_id": ...}
       ]
     }

Why This Architecture?
----------------------
1. **Maintainability**: Each domain expert can edit their module independently
2. **Scalability**: Adding new knowledge = adding new module + import
3. **Testability**: Each module can be unit tested in isolation
4. **Versioning**: Git history shows which knowledge changed when
5. **Clarity**: 200-line focused modules > 2000-line monolith
6. **Reusability**: Modules can be cherry-picked for different applications

The consolidator runs at bootstrap time, merging into ONE knowledge graph
that gets injected into the workspace's LightRAG instance.
"""

import logging
from typing import TypedDict

from src.ontology.govcon_kg_support import (
    build_ontology_stats,
    combine_knowledge_graph_parts,
    validate_custom_kg,
)

# Import all knowledge modules via package __init__
from src.ontology.knowledge import (
    # Shipley
    SHIPLEY_ENTITIES, SHIPLEY_RELATIONSHIPS, SHIPLEY_CHUNKS,
    # Regulations
    REGULATION_ENTITIES, REGULATION_RELATIONSHIPS, REGULATION_CHUNKS,
    # Evaluation
    EVALUATION_ENTITIES, EVALUATION_RELATIONSHIPS, EVALUATION_CHUNKS,
    # Workload
    WORKLOAD_ENTITIES, WORKLOAD_RELATIONSHIPS, WORKLOAD_CHUNKS,
    # Capture
    CAPTURE_ENTITIES, CAPTURE_RELATIONSHIPS, CAPTURE_CHUNKS,
    # Lessons Learned
    LESSONS_ENTITIES, LESSONS_RELATIONSHIPS, LESSONS_CHUNKS,
    # Company Capabilities
    COMPANY_ENTITIES, COMPANY_RELATIONSHIPS, COMPANY_CHUNKS,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Type Definitions (align with LightRAG custom_kg expected format)
# =============================================================================

class CustomEntity(TypedDict, total=False):
    """Entity structure for custom_kg['entities']."""
    entity_name: str      # Required: unique name
    entity_type: str      # Required: must be valid type from schema
    description: str      # Required: rich description for embedding
    source_id: str        # Optional: source identifier
    file_path: str        # Optional: file path reference
    # Additional optional fields from our modules
    process_phase: str    # Shipley phase
    rating_scale: str     # Evaluation rating
    threshold: str        # Performance threshold
    theme_type: str       # Strategic theme type


class CustomRelationship(TypedDict, total=False):
    """Relationship structure for custom_kg['relationships']."""
    src_id: str           # Required: source entity name
    tgt_id: str           # Required: target entity name
    description: str      # Required: relationship description
    keywords: str         # Required: MUST be a valid type from VALID_RELATIONSHIP_TYPES
    weight: float         # Optional: relationship strength (0-1)
    source_id: str        # Optional: source identifier
    file_path: str        # Optional: file path reference


class CustomChunk(TypedDict, total=False):
    """Chunk structure for custom_kg['chunks']."""
    content: str          # Required: text content for VDB
    source_id: str        # Optional: source identifier
    file_path: str        # Optional: file path reference


class CustomKnowledgeGraph(TypedDict):
    """Full custom_kg structure for insert_custom_kg()."""
    entities: list[CustomEntity]
    relationships: list[CustomRelationship]
    chunks: list[CustomChunk]


# =============================================================================
# Consolidation Logic
# =============================================================================

def build_govcon_ontology_kg() -> CustomKnowledgeGraph:
    """
    Consolidate all knowledge modules into single custom_kg dictionary.
    
    This function merges:
    - 6 knowledge modules
    - ~70 entities
    - ~50 relationships  
    - ~20 chunks
    
    Returns:
        CustomKnowledgeGraph: Combined knowledge graph ready for insert_custom_kg()
    
    Example:
        >>> kg = build_govcon_ontology_kg()
        >>> await rag.ainsert_custom_kg(kg)
    """
    combined = combine_knowledge_graph_parts(
        [
            (SHIPLEY_ENTITIES, SHIPLEY_RELATIONSHIPS, SHIPLEY_CHUNKS),
            (REGULATION_ENTITIES, REGULATION_RELATIONSHIPS, REGULATION_CHUNKS),
            (EVALUATION_ENTITIES, EVALUATION_RELATIONSHIPS, EVALUATION_CHUNKS),
            (WORKLOAD_ENTITIES, WORKLOAD_RELATIONSHIPS, WORKLOAD_CHUNKS),
            (CAPTURE_ENTITIES, CAPTURE_RELATIONSHIPS, CAPTURE_CHUNKS),
            (LESSONS_ENTITIES, LESSONS_RELATIONSHIPS, LESSONS_CHUNKS),
            (COMPANY_ENTITIES, COMPANY_RELATIONSHIPS, COMPANY_CHUNKS),
        ]
    )
    
    logger.info(
        f"Consolidated GovCon ontology: {len(combined['entities'])} entities, "
        f"{len(combined['relationships'])} relationships, {len(combined['chunks'])} chunks"
    )

    return combined


def get_ontology_stats() -> dict:
    """
    Get statistics about the consolidated ontology.
    
    Returns:
        dict: Counts by module and type
    
    Example:
        >>> stats = get_ontology_stats()
        >>> print(f"Total entities: {stats['total_entities']}")
    """
    return build_ontology_stats(
        {
            "shipley": (SHIPLEY_ENTITIES, SHIPLEY_RELATIONSHIPS, SHIPLEY_CHUNKS),
            "regulations": (REGULATION_ENTITIES, REGULATION_RELATIONSHIPS, REGULATION_CHUNKS),
            "evaluation": (EVALUATION_ENTITIES, EVALUATION_RELATIONSHIPS, EVALUATION_CHUNKS),
            "workload": (WORKLOAD_ENTITIES, WORKLOAD_RELATIONSHIPS, WORKLOAD_CHUNKS),
            "capture": (CAPTURE_ENTITIES, CAPTURE_RELATIONSHIPS, CAPTURE_CHUNKS),
            "lessons_learned": (LESSONS_ENTITIES, LESSONS_RELATIONSHIPS, LESSONS_CHUNKS),
            "company_capabilities": (COMPANY_ENTITIES, COMPANY_RELATIONSHIPS, COMPANY_CHUNKS),
        }
    )


def validate_ontology() -> tuple[bool, list[str]]:
    """
    Validate the consolidated ontology for common issues.
    
    Checks:
    - Required fields present in entities
    - Required fields present in relationships
    - Entity references in relationships exist
    - No duplicate entity names
    
    Returns:
        tuple[bool, list[str]]: (is_valid, list of error messages)
    """
    kg = build_govcon_ontology_kg()
    is_valid, errors = validate_custom_kg(kg)
    
    if is_valid:
        logger.info("Ontology validation passed")
    else:
        logger.warning(f"Ontology validation found {len(errors)} issues")
    
    return is_valid, errors


# =============================================================================
# Module-level singleton for efficiency
# =============================================================================

# Build once at import time for efficiency
# Subsequent calls to build_govcon_ontology_kg() will rebuild if needed
_CACHED_KG: CustomKnowledgeGraph | None = None


def get_govcon_ontology_kg() -> CustomKnowledgeGraph:
    """
    Get the consolidated GovCon ontology KG (cached).
    
    Use this function for normal operations to avoid rebuilding.
    Use build_govcon_ontology_kg() to force a rebuild.
    
    Returns:
        CustomKnowledgeGraph: Cached consolidated knowledge graph
    """
    global _CACHED_KG
    if _CACHED_KG is None:
        _CACHED_KG = build_govcon_ontology_kg()
    return _CACHED_KG


# =============================================================================
# CLI Support
# =============================================================================

if __name__ == "__main__":
    """
    Run directly for validation and stats:
        python -m src.ontology.govcon_kg
    """
    import json
    
    print("=" * 60)
    print("GovCon Domain Ontology KG Consolidator")
    print("=" * 60)
    
    # Get stats
    stats = get_ontology_stats()
    print("\n📊 Ontology Statistics:")
    print(f"   Total Entities:      {stats['total_entities']}")
    print(f"   Total Relationships: {stats['total_relationships']}")
    print(f"   Total Chunks:        {stats['total_chunks']}")
    
    print("\n📁 By Module:")
    for module, counts in stats["modules"].items():
        print(f"   {module}: {counts['entities']}E / {counts['relationships']}R / {counts['chunks']}C")
    
    # Validate
    print("\n🔍 Validating ontology...")
    is_valid, errors = validate_ontology()
    
    if is_valid:
        print("   ✅ Validation passed!")
    else:
        print(f"   ❌ Validation found {len(errors)} issues:")
        for error in errors[:10]:  # Show first 10
            print(f"      - {error}")
        if len(errors) > 10:
            print(f"      ... and {len(errors) - 10} more")
    
    # Sample output
    print("\n📝 Sample Entity:")
    kg = get_govcon_ontology_kg()
    if kg["entities"]:
        print(json.dumps(kg["entities"][0], indent=2)[:500])
    
    print("\n✅ Consolidator ready for use")
