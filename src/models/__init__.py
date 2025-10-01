"""
RFP Data Models Module

Contains Pydantic models defining our RFP ontology:
- RFPRequirement: Structured requirement representation
- ComplianceAssessment: Shipley 4-level compliance analysis
- SectionRelationship: Cross-section relationship modeling
- RFPAnalysisResult: Comprehensive analysis output

Provides the structured data foundation for our ontology-based RAG.
"""

from .rfp_models import (
    RFPRequirement, ComplianceAssessment, SectionRelationship, RFPSection,
    RFPAnalysisResult, ValidationResult, ProcessingMetadata,
    ComplianceLevel, RequirementType, ComplianceStatus, RiskLevel
)

__all__ = [
    'RFPRequirement',
    'ComplianceAssessment', 
    'SectionRelationship',
    'RFPSection',
    'RFPAnalysisResult',
    'ValidationResult',
    'ProcessingMetadata',
    'ComplianceLevel',
    'RequirementType', 
    'ComplianceStatus',
    'RiskLevel'
]