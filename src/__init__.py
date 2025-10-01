"""
GovCon Capture Vibe - Ontology-Based RAG for Government Contracting

A sophisticated RFP analysis system built on LightRAG with structured PydanticAI agents.
Implements Shipley methodology for government contracting compliance analysis.

Architecture:
- core/: LightRAG integration with RFP-aware processing
- agents/: PydanticAI structured agents for data validation  
- models/: Pydantic models defining RFP ontology
- api/: FastAPI routes for RFP analysis endpoints
- utils/: Logging, performance monitoring, and utilities

This system combines the power of knowledge graphs (LightRAG) with structured
AI agents (PydanticAI) to provide comprehensive RFP analysis capabilities.
"""

# Core LightRAG integration
from .core import (
    RFPAwareLightRAG, ShipleyRFPChunker, EnhancedRFPProcessor,
    ContextualChunk, RFPSection, RFPSubsection
)

# Structured AI agents
from .agents import RFPAnalysisAgents, RequirementsExtractionOutput, RFPContext

# Data models
from .models import (
    RFPRequirement, ComplianceAssessment, RFPAnalysisResult,
    ComplianceLevel, RequirementType, ComplianceStatus, RiskLevel
)

# Utilities
from .utils import setup_logging, get_monitor

__version__ = "2.0.0"
__all__ = [
    # Core components
    'RFPAwareLightRAG',
    'ShipleyRFPChunker', 
    'EnhancedRFPProcessor',
    'ContextualChunk',
    'RFPSection',
    'RFPSubsection',
    
    # AI agents
    'RFPAnalysisAgents',
    'RequirementsExtractionOutput',
    'RFPContext',
    
    # Data models
    'RFPRequirement',
    'ComplianceAssessment',
    'RFPAnalysisResult',
    'ComplianceLevel',
    'RequirementType',
    'ComplianceStatus', 
    'RiskLevel',
    
    # Utilities
    'setup_logging',
    'get_monitor'
]
