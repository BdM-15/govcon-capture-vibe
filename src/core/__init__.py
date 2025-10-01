"""
Core LightRAG Integration Module

Contains the core components for RFP-aware LightRAG integration:
- RFPAwareLightRAG: Enhanced LightRAG wrapper with RFP detection
- ShipleyRFPChunker: Section-aware chunking for government RFPs  
- EnhancedRFPProcessor: Orchestrates PydanticAI + LightRAG integration

This module forms the foundation of our ontology-based RAG architecture.
"""

from .lightrag_integration import RFPAwareLightRAG, process_rfp_with_lightrag
from .chunking import ShipleyRFPChunker, ContextualChunk, RFPSection, RFPSubsection
from .processor import EnhancedRFPProcessor

__all__ = [
    'RFPAwareLightRAG',
    'process_rfp_with_lightrag', 
    'ShipleyRFPChunker',
    'ContextualChunk',
    'RFPSection',
    'RFPSubsection',
    'EnhancedRFPProcessor'
]