"""
Relationship Inference Module

LLM-powered semantic relationship inference for Neo4j knowledge graphs.
Implements core algorithms for government contracting RFPs:

Active algorithms (Phase 4 of semantic post-processor):
1. L↔M Linking: proposal_instruction ↔ evaluation_factor (GUIDES/EVALUATED_BY)
2. Document Structure: section hierarchy and annex/attachment linking (CHILD_OF, DEFINES)
3. Orphan Resolution: unconnected entities → nearest related entity

Architecture (Issue #54 - Back to Basics):
- Entity extraction uses native LightRAG with the govcon ontology
- Post-processing uses Pydantic for relationship validation (InferredRelationship)
- No LLM-based entity type correction needed - native extraction handles it

Usage:
    from src.inference.semantic_post_processor import enhance_knowledge_graph
    from src.inference.neo4j_graph_io import Neo4jGraphIO, group_entities_by_type
    
    stats = await enhance_knowledge_graph(rag_storage_path, llm_func)
"""

from src.inference.neo4j_graph_io import (
    Neo4jGraphIO,
    group_entities_by_type,
)

__all__ = [
    # Neo4j Graph I/O exports
    "Neo4jGraphIO",
    "group_entities_by_type",
]
