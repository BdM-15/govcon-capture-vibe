"""
Structured RFP Data Models for PydanticAI Integration

Provides type-safe, validated data structures for government RFP analysis:
- Requirements extraction with Shipley methodology compliance
- Section relationship modeling 
- Compliance assessment with 4-level Shipley scale
- Universal compatibility across all government RFP formats

References:
- Shipley Proposal Guide p.50-55 (Requirements Analysis)
- Shipley Proposal Guide p.53-55 (Compliance Matrix)
- FAR 15.210 (Uniform RFP Format)
"""

from typing import List, Dict, Any, Optional, Literal, Union
from pydantic import BaseModel, Field, validator, root_validator
from enum import Enum
from datetime import datetime
import re

# Shipley Methodology Enums
class ComplianceLevel(str, Enum):
    """Shipley methodology requirement criticality levels"""
    MUST = "Must"      # Mandatory requirements (shall/must)
    SHOULD = "Should"  # Important requirements (should/will)
    MAY = "May"        # Optional requirements (may/could)
    WILL = "Will"      # Government commitments (not contractor requirements)

class ComplianceStatus(str, Enum):
    """Shipley 4-level compliance assessment scale"""
    COMPLIANT = "Compliant"          # Fully meets requirement
    PARTIAL = "Partial"              # Meets most aspects, minor gaps
    NON_COMPLIANT = "Non-Compliant"  # Cannot meet without major changes
    NOT_ADDRESSED = "Not Addressed"  # Requirement not covered

class RequirementType(str, Enum):
    """RFP requirement categorization"""
    FUNCTIONAL = "functional"        # What the system must do
    PERFORMANCE = "performance"      # How well it must perform
    INTERFACE = "interface"          # How it connects/communicates
    DESIGN = "design"               # Specific design constraints
    SECURITY = "security"           # Security and compliance requirements
    TECHNICAL = "technical"         # Technical specifications
    MANAGEMENT = "management"       # Project management requirements
    QUALITY = "quality"             # Quality assurance requirements
    ADMINISTRATIVE = "administrative" # Administrative/reporting requirements

class RiskLevel(str, Enum):
    """Risk assessment levels for compliance gaps"""
    HIGH = "High"       # Critical to mission, high evaluation weight
    MEDIUM = "Medium"   # Important but manageable
    LOW = "Low"         # Minor impact, easily mitigated

class RFPSectionType(str, Enum):
    """Standard government RFP sections per FAR 15.210"""
    A = "A"  # Solicitation/Contract Form
    B = "B"  # Supplies or Services and Prices/Costs
    C = "C"  # Statement of Work
    D = "D"  # Packaging and Marking
    E = "E"  # Inspection and Acceptance
    F = "F"  # Deliveries or Performance
    G = "G"  # Contract Administration Data
    H = "H"  # Special Contract Requirements
    I = "I"  # Contract Clauses
    J = "J"  # List of Attachments
    K = "K"  # Representations, Certifications and Other Statements
    L = "L"  # Instructions to Offerors
    M = "M"  # Evaluation Factors for Award

# Core RFP Data Models

class RFPRequirement(BaseModel):
    """
    Structured requirement with Shipley methodology compliance
    
    Represents a single requirement extracted from RFP with full context
    and traceability for compliance matrix development.
    """
    requirement_id: str = Field(..., description="Unique requirement identifier (REQ-XXX-001)")
    requirement_text: str = Field(..., description="Exact verbatim text from RFP")
    section_id: str = Field(..., description="RFP section (A, B, C, L, M, etc.)")
    subsection_id: Optional[str] = Field(None, description="Specific subsection (L.3.1, M.2.5)")
    
    # Shipley Classification
    compliance_level: ComplianceLevel = Field(..., description="Shipley criticality assessment")
    requirement_type: RequirementType = Field(..., description="Requirement categorization")
    
    # Context and Traceability
    page_reference: Optional[str] = Field(None, description="Page number or reference")
    source_context: Optional[str] = Field(None, description="Surrounding text for context")
    dependencies: List[str] = Field(default_factory=list, description="Related requirement IDs")
    
    # Analysis Metadata
    keywords: List[str] = Field(default_factory=list, description="Key terms for searchability")
    shipley_reference: Optional[str] = Field(None, description="Shipley Guide page reference")
    extracted_at: datetime = Field(default_factory=datetime.now)
    
    @validator('requirement_id')
    def validate_requirement_id(cls, v):
        """Ensure requirement ID follows standard format"""
        if not re.match(r'^REQ-[A-Z\d]+-\d{3}$', v):
            raise ValueError('requirement_id must follow format REQ-XXX-001')
        return v
    
    @validator('section_id')
    def validate_section_id(cls, v):
        """Ensure section ID is valid RFP section"""
        if not re.match(r'^[A-MJ](-\w+)?$', v):
            raise ValueError('section_id must be valid RFP section (A-M or J-attachment)')
        return v

class ComplianceAssessment(BaseModel):
    """
    Shipley methodology compliance assessment for proposal development
    
    Links requirements to proposal responses with gap analysis
    and recommendations following Shipley Guide standards.
    """
    requirement_id: str = Field(..., description="Reference to RFPRequirement")
    requirement_text: str = Field(..., description="Requirement being assessed")
    
    # Shipley Compliance Analysis
    compliance_status: ComplianceStatus = Field(..., description="Shipley 4-level assessment")
    proposal_section: Optional[str] = Field(None, description="Where addressed in proposal")
    proposal_evidence: Optional[str] = Field(None, description="Specific proposal text/evidence")
    
    # Gap Analysis (Shipley Capture Guide p.85-90)
    gap_description: Optional[str] = Field(None, description="Detailed gap analysis")
    risk_level: RiskLevel = Field(..., description="Risk assessment for gaps")
    mitigation_strategy: Optional[str] = Field(None, description="Risk mitigation approach")
    
    # Win Theme Development
    competitive_advantage: Optional[str] = Field(None, description="Opportunity for differentiation")
    win_theme_alignment: Optional[str] = Field(None, description="How this supports win themes")
    
    # Action Planning
    recommendations: List[str] = Field(default_factory=list, description="Specific action items")
    assigned_to: Optional[str] = Field(None, description="Responsible team member")
    due_date: Optional[datetime] = Field(None, description="Completion deadline")
    
    # Shipley Methodology References
    shipley_reference: str = Field(default="Shipley Proposal Guide p.53-55", description="Methodology source")
    assessed_at: datetime = Field(default_factory=datetime.now)

class SectionRelationship(BaseModel):
    """
    Models relationships between RFP sections for comprehensive analysis
    
    Critical for understanding L↔M connections and cross-section dependencies
    that affect proposal strategy and compliance.
    """
    source_section: str = Field(..., description="Source section ID")
    target_section: str = Field(..., description="Related section ID")
    relationship_type: Literal["references", "depends_on", "evaluates", "supports", "requires"] = Field(
        ..., description="Type of relationship"
    )
    description: str = Field(..., description="Description of the relationship")
    importance: Literal["critical", "important", "informational"] = Field(
        ..., description="Relationship importance level"
    )
    
    # Examples of specific relationships
    examples: List[str] = Field(default_factory=list, description="Specific examples of connection")
    
class RFPSection(BaseModel):
    """
    Complete RFP section with enhanced metadata and content analysis
    
    Preserves section structure while enabling sophisticated analysis
    and cross-referencing capabilities.
    """
    section_id: str = Field(..., description="Section identifier (A, B, C, etc.)")
    section_title: str = Field(..., description="Official section title")
    content: str = Field(..., description="Full section content")
    
    # Structure and Organization
    subsections: List[str] = Field(default_factory=list, description="Identified subsections")
    page_range: Optional[str] = Field(None, description="Page range (e.g., '45-67')")
    word_count: int = Field(default=0, description="Section word count")
    
    # Requirements Analysis
    requirements: List[RFPRequirement] = Field(default_factory=list, description="Extracted requirements")
    requirements_count: int = Field(default=0, description="Total requirements count")
    critical_requirements_count: int = Field(default=0, description="Must/Shall requirements count")
    
    # Relationships
    related_sections: List[SectionRelationship] = Field(default_factory=list, description="Section relationships")
    
    # Analysis Metadata
    contains_evaluation_criteria: bool = Field(default=False, description="Contains evaluation factors")
    contains_instructions: bool = Field(default=False, description="Contains submission instructions")
    contains_specifications: bool = Field(default=False, description="Contains technical specs")
    analysis_confidence: float = Field(default=0.0, description="Analysis confidence score (0-1)")

class RFPAnalysisResult(BaseModel):
    """
    Comprehensive RFP analysis results with Shipley methodology integration
    
    Aggregates all analysis components for proposal development and
    strategic planning with full traceability and methodology compliance.
    """
    # Document Metadata
    rfp_title: str = Field(..., description="RFP title or subject")
    solicitation_number: str = Field(..., description="Government solicitation number")
    agency: Optional[str] = Field(None, description="Issuing agency")
    analysis_date: datetime = Field(default_factory=datetime.now)
    
    # Section Analysis
    sections: List[RFPSection] = Field(default_factory=list, description="All RFP sections")
    total_sections: int = Field(default=0, description="Total sections identified")
    sections_with_requirements: int = Field(default=0, description="Sections containing requirements")
    
    # Requirements Summary
    total_requirements: int = Field(default=0, description="Total requirements extracted")
    requirements_by_level: Dict[str, int] = Field(default_factory=dict, description="Requirements by criticality")
    requirements_by_type: Dict[str, int] = Field(default_factory=dict, description="Requirements by category")
    
    # Section Relationships
    section_relationships: List[SectionRelationship] = Field(default_factory=list, description="Inter-section connections")
    critical_relationships: List[str] = Field(default_factory=list, description="Key relationship descriptions")
    
    # Shipley Methodology Application
    shipley_compliance_matrix: List[ComplianceAssessment] = Field(default_factory=list, description="Compliance assessments")
    gap_analysis_summary: Dict[str, Any] = Field(default_factory=dict, description="Overall gap analysis")
    win_themes_identified: List[str] = Field(default_factory=list, description="Potential win themes")
    
    # Quality Metrics
    analysis_quality_score: float = Field(default=0.0, description="Overall analysis quality (0-1)")
    confidence_metrics: Dict[str, float] = Field(default_factory=dict, description="Confidence by analysis type")
    
    # References and Methodology
    shipley_references: List[str] = Field(default_factory=list, description="Shipley Guide references used")
    methodology_notes: List[str] = Field(default_factory=list, description="Analysis methodology notes")

# Validation and Helper Models

class ValidationResult(BaseModel):
    """Results of data validation operations"""
    is_valid: bool = Field(..., description="Overall validation status")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    suggestions: List[str] = Field(default_factory=list, description="Improvement suggestions")
    validation_timestamp: datetime = Field(default_factory=datetime.now)

class ProcessingMetadata(BaseModel):
    """Metadata about the processing pipeline"""
    processor_version: str = Field(default="1.0", description="Processing pipeline version")
    lightrag_version: Optional[str] = Field(None, description="LightRAG version used")
    pydantic_ai_version: Optional[str] = Field(None, description="PydanticAI version used")
    processing_time_seconds: float = Field(default=0.0, description="Total processing time")
    chunk_count: int = Field(default=0, description="Number of chunks processed")
    model_used: str = Field(default="qwen2.5-coder:7b", description="LLM model used")
    
# Export all models for easy importing
__all__ = [
    'ComplianceLevel', 'ComplianceStatus', 'RequirementType', 'RiskLevel', 'RFPSectionType',
    'RFPRequirement', 'ComplianceAssessment', 'SectionRelationship', 'RFPSection', 
    'RFPAnalysisResult', 'ValidationResult', 'ProcessingMetadata'
]