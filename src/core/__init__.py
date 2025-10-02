"""
Core LightRAG Integration Module

Contains the core components for RFP-aware LightRAG integration:
- ShipleyRFPChunker: Section-aware chunking for government RFPs  
- rfp_aware_chunking_func: LightRAG extension point for section-aware chunking

This module forms the foundation of our ontology-based RAG architecture.
"""

# Only import what doesn't have circular dependencies
from .chunking import ShipleyRFPChunker, ContextualChunk, RFPSection, RFPSubsection
from .lightrag_chunking import rfp_aware_chunking_func

__all__ = [
    'ShipleyRFPChunker',
    'ContextualChunk',
    'RFPSection',
    'RFPSubsection',
    'rfp_aware_chunking_func'
]