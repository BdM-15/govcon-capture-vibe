"""
RFP Data Models for Structured Requirements Extraction

This module defines Pydantic models for structured representation of RFP requirements
and related data following Shipley Proposal Guide best practices and Federal Acquisition 
Regulation (FAR) compliance frameworks.

FLEXIBLE EVALUATION CRITERIA SYSTEM:
This system handles both standard federal evaluation criteria (Technical Approach, 
Past Performance, etc.) and custom/unique factors (Total Compensation, Innovation 
Capability, Cultural Competency, etc.) that agencies may use. The EvaluationFactor 
model can map custom factors to standard categories where appropriate, while preserving 
the original agency language and requirements.

Key Features:
- StandardEvaluationCriteria enum for common federal factors
- EvaluationFactor model for flexible factor representation  
- EvaluationScheme model for complete evaluation methodology
- EvaluationCriteriaParser for automated factor extraction and categorization
- CustomEvaluationExamples for learning from non-standard factors

This approach ensures we can handle any evaluation criteria while maintaining 
structure and consistency for proposal development and compliance checking.

Reason: Uses Pydantic for type safety and validation; structures align with government 
RFP format (A-M sections), Shipley compliance frameworks, and federal procurement standards.
Adapted from AI RFP Simulator evaluation methodology for government contracting context.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, validator


class ComplianceType(str, Enum):
    """Compliance classification based on RFP language analysis per FAR standards."""
    MANDATORY = "mandatory"      # "shall", "must", "required" - FAR mandatory compliance
    DESIRED = "desired"         # "should", "preferred", "desired" - evaluation factors
    OPTIONAL = "optional"       # "may", "can", "optional" - value-added features


class RFPSection(str, Enum):
    """Standard RFP sections based on UCF (Uniform Contract Format) per FAR Part 15."""
    SECTION_A = "A"  # Solicitation/Contract Form (SF-33, SF-1449)
    SECTION_B = "B"  # Supplies or Services and Prices/Costs
    SECTION_C = "C"  # Description/Specs/Work Statement (SOW/PWS)
    SECTION_D = "D"  # Packaging and Marking
    SECTION_E = "E"  # Inspection and Acceptance
    SECTION_F = "F"  # Deliveries or Performance
    SECTION_G = "G"  # Contract Administration Data
    SECTION_H = "H"  # Special Contract Requirements
    SECTION_I = "I"  # Contract Clauses (FAR/DFARS clauses)
    SECTION_J = "J"  # List of Attachments
    SECTION_K = "K"  # Representations, Certifications and Other Statements
    SECTION_L = "L"  # Instructions, Conditions, and Notices to Offerors
    SECTION_M = "M"  # Evaluation Factors for Award (Best Value/LPTA)
    OTHER = "OTHER"  # Non-standard sections


class StandardEvaluationCriteria(str, Enum):
    """Standard federal evaluation criteria types per FAR Part 15."""
    TECHNICAL_APPROACH = "technical_approach"      # Technical solution quality
    PAST_PERFORMANCE = "past_performance"         # Contractor performance history
    MANAGEMENT_APPROACH = "management_approach"    # Project management methodology
    KEY_PERSONNEL = "key_personnel"               # Staff qualifications
    CORPORATE_EXPERIENCE = "corporate_experience"  # Company capabilities
    PRICE_COST = "price_cost"                     # Cost/price evaluation
    SMALL_BUSINESS = "small_business"             # Small business participation
    SECURITY_CLEARANCE = "security_clearance"     # Personnel security requirements
    OTHER = "other"                               # Custom/non-standard criteria


class EvaluationFactor(BaseModel):
    """
    Flexible evaluation factor that can handle both standard and custom criteria.
    
    Reason: Accommodates unique agency requirements while maintaining structure
    for common federal evaluation patterns. Supports complex weighting schemes.
    """
    factor_id: str = Field(..., description="Unique factor identifier")
    factor_name: str = Field(..., description="Evaluation factor name as stated in RFP")
    standard_category: Optional[StandardEvaluationCriteria] = Field(None, description="Maps to standard category if applicable")
    weight_percentage: Optional[float] = Field(None, description="Evaluation weight (0-100)")
    weight_points: Optional[int] = Field(None, description="Point value if point-based system")
    
    # Detailed factor information
    description: str = Field(default="", description="Full factor description from RFP")
    subfactors: List[str] = Field(default_factory=list, description="Sub-evaluation factors")
    evaluation_method: Optional[str] = Field(None, description="How this factor will be evaluated")
    
    # Source tracking
    rfp_section: Optional[str] = Field(None, description="Source section (usually Section M)")
    page_reference: Optional[str] = Field(None, description="Page number or reference")
    
    # Custom attributes for unique factors
    custom_attributes: Dict[str, Any] = Field(default_factory=dict, description="Agency-specific attributes")
    
    @validator('factor_name')
    def clean_factor_name(cls, v):
        """Clean and standardize factor names."""
        return v.strip().title()
    
    @validator('weight_percentage')
    def validate_weight(cls, v):
        """Ensure weight is between 0 and 100."""
        if v is not None and (v < 0 or v > 100):
            raise ValueError("Weight percentage must be between 0 and 100")
        return v


class EvaluationScheme(BaseModel):
    """
    Complete evaluation scheme for an RFP.
    
    Handles various federal evaluation approaches including Best Value Trade-off,
    Lowest Price Technically Acceptable (LPTA), and custom scoring systems.
    """
    scheme_type: str = Field(..., description="Best Value Trade-off, LPTA, Points-based, etc.")
    total_points: Optional[int] = Field(None, description="Total points possible")
    factors: List[EvaluationFactor] = Field(default_factory=list, description="All evaluation factors")
    
    # Validation rules
    weights_sum_to_100: bool = Field(True, description="Whether weights must sum to 100%")
    has_price_factor: bool = Field(False, description="Whether price/cost is an evaluation factor")
    
    # Special considerations
    adjectival_ratings: List[str] = Field(default_factory=list, description="Adjectival rating scale (Excellent, Good, etc.)")
    color_ratings: List[str] = Field(default_factory=list, description="Color rating scale (Blue, Green, Yellow, Red)")
    
    @validator('factors')
    def validate_factor_weights(cls, v, values):
        """Validate that weights are reasonable if weights_sum_to_100 is True."""
        if values.get('weights_sum_to_100', True):
            total_weight = sum(f.weight_percentage or 0 for f in v if f.weight_percentage is not None)
            if len([f for f in v if f.weight_percentage is not None]) > 0 and abs(total_weight - 100) > 1:
                # Allow 1% tolerance for rounding
                raise ValueError(f"Factor weights sum to {total_weight}%, should be approximately 100%")
        return v


class ContractType(str, Enum):
    """Federal contract types per FAR Part 16."""
    FIRM_FIXED_PRICE = "ffp"          # Firm Fixed Price
    FIXED_PRICE_INCENTIVE = "fpi"     # Fixed Price Incentive
    COST_PLUS_FIXED_FEE = "cpff"      # Cost Plus Fixed Fee
    COST_PLUS_INCENTIVE = "cpif"      # Cost Plus Incentive Fee
    TIME_AND_MATERIALS = "tm"         # Time and Materials
    LABOR_HOUR = "lh"                 # Labor Hour
    INDEFINITE_DELIVERY = "idiq"      # Indefinite Delivery/Indefinite Quantity


class RequirementComplexity(str, Enum):
    """Classification of requirement complexity for parsing strategy."""
    SIMPLE = "simple"              # Single, clear requirement
    COMPOUND = "compound"          # Multiple requirements in one paragraph
    NESTED = "nested"              # Requirements with sub-requirements
    CROSS_REFERENCED = "cross_referenced"  # References other sections/requirements


class RequirementFragment(BaseModel):
    """
    Individual requirement fragment extracted from compound paragraphs.
    
    Reason: Many federal RFPs contain compound paragraphs with multiple distinct
    requirements. This model allows decomposition while maintaining traceability
    to the source paragraph.
    """
    fragment_id: str = Field(..., description="Unique fragment identifier (REQ-001-A format)")
    parent_req_id: str = Field(..., description="Parent requirement ID")
    description: str = Field(..., description="Individual requirement fragment text")
    compliance_type: ComplianceType = Field(..., description="Mandatory/desired/optional classification")
    key_phrases: List[str] = Field(default_factory=list, description="Key action phrases (demonstrates, ensures, etc.)")
    related_fragments: List[str] = Field(default_factory=list, description="Related fragment IDs")
    
    @validator('fragment_id')
    def validate_fragment_id(cls, v, values):
        """Ensure fragment ID follows REQ-XXX-A format."""
        if 'parent_req_id' in values:
            parent_id = values['parent_req_id']
            if not v.startswith(f"{parent_id}-"):
                v = f"{parent_id}-{v.split('-')[-1] if '-' in v else 'A'}"
        return v.upper()


class Requirement(BaseModel):
    """
    Individual requirement extracted from RFP documents.
    
    Enhanced to handle compound requirements common in federal RFPs.
    Grounded in Shipley Proposal Guide p.50 compliance checklist structure.
    """
    req_id: str = Field(..., description="Unique requirement identifier (REQ-XXXX format)")
    section: RFPSection = Field(..., description="RFP section where requirement appears")
    description: str = Field(..., description="Full requirement text (may be compound)")
    compliance_type: ComplianceType = Field(..., description="Mandatory/desired/optional classification")
    rfp_ref: str = Field(..., description="Citation to RFP section/page (e.g., 'Section C.3.2.1, Page 45')")
    snippet: str = Field(..., description="Key excerpt from RFP text for verification")
    
    # Compound requirement handling
    complexity: RequirementComplexity = Field(default=RequirementComplexity.SIMPLE, description="Requirement complexity type")
    fragments: List[RequirementFragment] = Field(default_factory=list, description="Individual requirement fragments if compound")
    source_paragraph: Optional[str] = Field(None, description="Full source paragraph for compound requirements")
    
    # Standard fields
    sub_factors: List[str] = Field(default_factory=list, description="Sub-requirements or evaluation factors")
    
    # Enhanced attributes based on AI RFP Simulator methodology
    evaluation_factors: List[str] = Field(default_factory=list, description="Associated evaluation factor names")
    weight_percentage: Optional[float] = Field(None, description="Evaluation weight (0-100)")
    deliverable_required: bool = Field(False, description="Requires specific deliverable")
    security_level: Optional[str] = Field(None, description="Security classification if applicable")
    
    # Shipley-specific fields
    compliance_risk: str = Field(default="medium", description="Risk level: low/medium/high")
    win_themes: List[str] = Field(default_factory=list, description="Associated win themes")
    discriminators: List[str] = Field(default_factory=list, description="Key differentiators")
    
    # Cross-reference tracking
    references_sections: List[str] = Field(default_factory=list, description="Referenced RFP sections")
    references_attachments: List[str] = Field(default_factory=list, description="Referenced attachments")
    
    attributes: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    
    @validator('req_id')
    def validate_req_id(cls, v):
        """Ensure requirement ID follows federal standard format."""
        if not v or len(v.strip()) == 0:
            raise ValueError("Requirement ID cannot be empty")
        # Enforce REQ-XXXX format for government contracts
        if not v.upper().startswith('REQ-'):
            v = f"REQ-{v}"
        return v.strip().upper()
    
    def get_all_requirements(self) -> List[Dict[str, Any]]:
        """
        Get all requirements including fragments for compliance checking.
        
        Returns:
            List of all individual requirements (main + fragments)
        """
        requirements = [{"id": self.req_id, "description": self.description, "type": "main"}]
        
        for fragment in self.fragments:
            requirements.append({
                "id": fragment.fragment_id,
                "description": fragment.description,
                "type": "fragment",
                "parent": self.req_id
            })
        
        return requirements


class RFPAnalysisAttribute(BaseModel):
    """
    Structured attribute extracted from RFP analysis.
    
    Based on AI RFP Simulator 15-attribute model, adapted for federal contracting.
    """
    id: str = Field(..., description="Attribute identifier")
    name: str = Field(..., description="Attribute name")
    content: str = Field(..., description="Extracted content")
    source_snippet: str = Field(..., description="Original text snippet")
    page_number: Optional[int] = Field(None, description="Source page number")
    section_title: Optional[str] = Field(None, description="Source section title")
    confidence_score: float = Field(default=0.0, description="Extraction confidence (0.0-1.0)")
    extracted_at: datetime = Field(default_factory=datetime.now, description="Extraction timestamp")


class FederalRFPAttributes(BaseModel):
    """
    15 key attributes for federal RFP analysis based on FAR requirements.
    
    Adapted from AI RFP Simulator methodology for federal procurement context.
    """
    # Core Project Information
    issuing_agency: RFPAnalysisAttribute = Field(..., description="Federal agency or department")
    contracting_office: RFPAnalysisAttribute = Field(..., description="Contracting office and POC")
    project_background: RFPAnalysisAttribute = Field(..., description="Mission need and problem statement")
    project_objectives: RFPAnalysisAttribute = Field(..., description="Performance objectives and outcomes")
    project_scope: RFPAnalysisAttribute = Field(..., description="Scope of work and boundaries")
    
    # Contract Details
    project_period: RFPAnalysisAttribute = Field(..., description="Period of performance")
    contract_value: RFPAnalysisAttribute = Field(..., description="Estimated contract value/ceiling")
    contract_type: RFPAnalysisAttribute = Field(..., description="Contract type (FFP, CPFF, etc.)")
    
    # Evaluation Framework
    evaluation_scheme: RFPAnalysisAttribute = Field(..., description="Complete evaluation methodology and factors")
    required_deliverables: RFPAnalysisAttribute = Field(..., description="Required deliverables and standards")
    
    # Contractor Requirements
    contractor_qualifications: RFPAnalysisAttribute = Field(..., description="Required qualifications and experience")
    security_requirements: RFPAnalysisAttribute = Field(..., description="Security clearance and compliance")
    compliance_requirements: RFPAnalysisAttribute = Field(..., description="FAR/DFARS and regulatory compliance")
    
    # Process Details
    procurement_schedule: RFPAnalysisAttribute = Field(..., description="Solicitation and award timeline")
    special_conditions: RFPAnalysisAttribute = Field(..., description="Special terms and conditions")


class DocumentMetadata(BaseModel):
    """Metadata about the processed RFP document."""
    file_name: str = Field(..., description="Original file name")
    file_size: int = Field(..., description="File size in bytes")
    page_count: Optional[int] = Field(None, description="Number of pages (for PDFs)")
    processing_date: datetime = Field(default_factory=datetime.now, description="When document was processed")
    document_type: str = Field(..., description="PDF, DOCX, etc.")
    checksum: Optional[str] = Field(None, description="File hash for integrity")
    
    # Federal-specific metadata
    solicitation_number: Optional[str] = Field(None, description="Federal solicitation number")
    naics_code: Optional[str] = Field(None, description="NAICS code classification")
    set_aside_type: Optional[str] = Field(None, description="Small business set-aside type")


class ShipleyAssessment(BaseModel):
    """
    Shipley methodology assessment results.
    
    Based on Shipley Capture Guide and Proposal Guide evaluation frameworks.
    """
    win_probability: float = Field(..., description="Win probability assessment (0.0-1.0)")
    competitive_position: str = Field(..., description="Strong/Moderate/Weak competitive position")
    key_win_themes: List[str] = Field(..., description="Primary win themes identified")
    key_discriminators: List[str] = Field(..., description="Key differentiating factors")
    compliance_gaps: List[str] = Field(default_factory=list, description="Identified compliance gaps")
    risk_factors: List[str] = Field(default_factory=list, description="Key risk factors")
    recommended_strategy: str = Field(..., description="Recommended bid strategy")
    capture_readiness: str = Field(..., description="Ready/Caution/No-Bid recommendation")


class ExtractionResult(BaseModel):
    """
    Complete result of RFP requirement extraction process.
    
    Enhanced with federal contracting and Shipley methodology elements.
    """
    document_metadata: DocumentMetadata = Field(..., description="Source document information")
    requirements: List[Requirement] = Field(..., description="Extracted requirements list")
    federal_attributes: FederalRFPAttributes = Field(..., description="15 key federal RFP attributes")
    shipley_assessment: Optional[ShipleyAssessment] = Field(None, description="Shipley methodology assessment")
    
    # Summary metrics
    total_requirements: int = Field(..., description="Total number of requirements found")
    extraction_summary: Dict[str, int] = Field(..., description="Summary by section/type")
    processing_time: float = Field(..., description="Processing time in seconds")
    
    # References
    shipley_ref: str = Field(default="Proposal Guide p.50", description="Shipley reference used")
    far_compliance: bool = Field(default=True, description="FAR compliance validation")
    
    @validator('total_requirements')
    def validate_total_requirements(cls, v, values):
        """Ensure total matches actual requirements count."""
        if 'requirements' in values:
            actual_count = len(values['requirements'])
            if v != actual_count:
                raise ValueError(f"Total requirements ({v}) doesn't match actual count ({actual_count})")
        return v


class RFPOverview(BaseModel):
    """
    High-level overview of RFP for initial assessment.
    
    Grounded in Shipley Capture Guide strategic assessment framework
    and federal procurement standards.
    """
    # Federal identification
    solicitation_number: Optional[str] = Field(None, description="Federal solicitation number")
    title: Optional[str] = Field(None, description="RFP title/subject")
    issuing_agency: Optional[str] = Field(None, description="Federal agency/department")
    contracting_office: Optional[str] = Field(None, description="Contracting office")
    
    # Key dates and values
    due_date: Optional[datetime] = Field(None, description="Proposal due date")
    contract_value: Optional[str] = Field(None, description="Estimated contract value")
    period_of_performance: Optional[str] = Field(None, description="Contract duration")
    
    # Technical scope
    key_scope: List[str] = Field(default_factory=list, description="Main scope elements")
    evaluation_criteria: List[str] = Field(default_factory=list, description="Key evaluation factors")
    
    # Federal-specific elements
    contract_type: Optional[ContractType] = Field(None, description="Contract type")
    naics_code: Optional[str] = Field(None, description="NAICS code")
    set_aside_type: Optional[str] = Field(None, description="Set-aside classification")
    security_clearance_required: bool = Field(False, description="Security clearance required")
    
    # Shipley assessment preview
    initial_win_probability: Optional[float] = Field(None, description="Initial win probability (0.0-1.0)")
    competitive_landscape: Optional[str] = Field(None, description="Competitive environment assessment")
    

class ProcessingStatus(BaseModel):
    """Status tracking for document processing pipeline."""
    status: str = Field(..., description="Current processing status")
    stage: str = Field(..., description="Current processing stage")
    progress: float = Field(default=0.0, description="Progress percentage (0-100)")
    message: str = Field(default="", description="Status message")
    error: Optional[str] = Field(None, description="Error message if failed")
    started_at: datetime = Field(default_factory=datetime.now, description="Processing start time")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update time")


class QueryResult(BaseModel):
    """Result from LightRAG query operations."""
    query: str = Field(..., description="Original query text")
    response: str = Field(..., description="Generated response")
    context_sources: List[str] = Field(default_factory=list, description="Source citations")
    confidence_score: float = Field(default=0.0, description="Response confidence (0.0-1.0)")
    query_time: float = Field(..., description="Query execution time in seconds")
    mode: str = Field(default="hybrid", description="LightRAG query mode used")


class EvaluationCriteriaParser(BaseModel):
    """
    Utility class for parsing and categorizing evaluation criteria from RFP text.
    
    Reason: Provides structured approach to handle both standard and custom 
    evaluation factors while maintaining consistency with federal procurement patterns.
    """
    
    # Common evaluation criteria patterns and their indicators
    STANDARD_PATTERNS = {
        "technical_approach": [
            "technical approach", "technical solution", "technical methodology",
            "system design", "architecture", "technical feasibility"
        ],
        "past_performance": [
            "past performance", "prior experience", "performance history",
            "relevant experience", "similar projects", "track record"
        ],
        "management_approach": [
            "management approach", "project management", "program management",
            "management plan", "management methodology", "management structure"
        ],
        "key_personnel": [
            "key personnel", "project manager", "technical lead", "staff qualifications",
            "personnel qualifications", "team members", "key staff"
        ],
        "corporate_experience": [
            "corporate experience", "company experience", "organizational capability",
            "corporate capability", "firm experience", "business experience"
        ],
        "price_cost": [
            "price", "cost", "pricing", "total evaluated price", "cost proposal",
            "price evaluation", "cost evaluation", "financial proposal"
        ],
        "small_business": [
            "small business", "small business utilization", "subcontracting plan",
            "small business participation", "small business goals"
        ],
        "security_clearance": [
            "security clearance", "personnel security", "clearance requirements",
            "security requirements", "cleared personnel"
        ]
    }
    
    @classmethod
    def categorize_factor(cls, factor_name: str, factor_description: str = "") -> StandardEvaluationCriteria:
        """
        Attempt to categorize a custom evaluation factor into standard categories.
        
        Args:
            factor_name: The name of the evaluation factor
            factor_description: Additional description text
            
        Returns:
            Best matching standard category or OTHER if no match
        """
        combined_text = f"{factor_name} {factor_description}".lower()
        
        for category, patterns in cls.STANDARD_PATTERNS.items():
            if any(pattern in combined_text for pattern in patterns):
                return StandardEvaluationCriteria(category)
        
        return StandardEvaluationCriteria.OTHER
    
    @classmethod
    def extract_evaluation_factors(cls, section_m_text: str) -> List[EvaluationFactor]:
        """
        Extract evaluation factors from Section M text.
        
        This method uses pattern matching and NLP techniques to identify
        evaluation factors, their weights, and subfactors from RFP text.
        
        Args:
            section_m_text: Text from Section M (Evaluation Factors for Award)
            
        Returns:
            List of structured evaluation factors
        """
        # This would be implemented with more sophisticated NLP
        # For now, providing structure for the implementation
        factors = []
        
        # Example patterns to look for:
        # "Technical Approach (40 points)"
        # "Past Performance - 30%"
        # "1. Technical Solution (Weight: 40%)"
        
        # Placeholder implementation - would use regex and NLP in production
        import re
        
        # Pattern for factors with percentages
        percentage_pattern = r'([A-Za-z\s]+?)\s*[-:()]*\s*(\d+)%'
        # Pattern for factors with points
        points_pattern = r'([A-Za-z\s]+?)\s*[-:()]*\s*(\d+)\s*points?'
        
        for match in re.finditer(percentage_pattern, section_m_text, re.IGNORECASE):
            factor_name = match.group(1).strip()
            weight = float(match.group(2))
            
            factor = EvaluationFactor(
                factor_id=f"EVAL-{len(factors)+1:03d}",
                factor_name=factor_name,
                standard_category=cls.categorize_factor(factor_name),
                weight_percentage=weight,
                rfp_section="Section M"
            )
            factors.append(factor)
        
        for match in re.finditer(points_pattern, section_m_text, re.IGNORECASE):
            factor_name = match.group(1).strip()
            points = int(match.group(2))
            
            # Skip if we already found this factor with percentage
            if not any(f.factor_name.lower() == factor_name.lower() for f in factors):
                factor = EvaluationFactor(
                    factor_id=f"EVAL-{len(factors)+1:03d}",
                    factor_name=factor_name,
                    standard_category=cls.categorize_factor(factor_name),
                    weight_points=points,
                    rfp_section="Section M"
                )
                factors.append(factor)
        
        return factors


class CompoundRequirementParser(BaseModel):
    """
    Specialized parser for handling compound requirement paragraphs.
    
    Federal RFPs often contain dense paragraphs with multiple distinct requirements.
    This parser uses linguistic patterns and domain knowledge to decompose them.
    """
    
    # Common requirement trigger phrases in federal RFPs
    REQUIREMENT_TRIGGERS = [
        # Demonstration requirements
        "demonstrates", "demonstrate", "demonstrating",
        "shows", "show", "showing", "exhibits", "exhibit",
        
        # Performance requirements  
        "performs", "perform", "performing", "achieves", "achieve",
        "accomplishes", "accomplish", "ensures", "ensure",
        
        # Understanding requirements
        "understands", "understand", "understanding",
        "comprehends", "comprehend", "recognizes", "recognize",
        
        # Approach/methodology requirements
        "approaches", "approach", "methodology", "method",
        "procedures", "procedure", "processes", "process",
        
        # Compliance requirements
        "adheres", "adhere", "complies", "comply", "follows", "follow",
        "conforms", "conform", "meets", "meet",
        
        # Capability requirements
        "provides", "provide", "delivers", "deliver",
        "maintains", "maintain", "supports", "support"
    ]
    
    # Phrases that indicate separate requirements
    SEPARATION_INDICATORS = [
        "the offeror", "the contractor", "the methodology",
        "the approach", "the solution", "the system",
        ". the", "additionally", "furthermore", "moreover",
        "in addition", "also demonstrates", "also shows"
    ]
    
    @classmethod
    def identify_complexity(cls, requirement_text: str) -> RequirementComplexity:
        """
        Identify the complexity level of a requirement paragraph.
        
        Args:
            requirement_text: The requirement paragraph text
            
        Returns:
            RequirementComplexity classification
        """
        text_lower = requirement_text.lower()
        
        # Count requirement triggers
        trigger_count = sum(1 for trigger in cls.REQUIREMENT_TRIGGERS if trigger in text_lower)
        
        # Count separation indicators
        separation_count = sum(1 for indicator in cls.SEPARATION_INDICATORS if indicator in text_lower)
        
        # Check for cross-references
        has_cross_refs = any(ref in text_lower for ref in ["section", "annex", "attachment", "spec item"])
        
        # Classification logic
        if trigger_count >= 5 and separation_count >= 3:
            return RequirementComplexity.COMPOUND
        elif has_cross_refs and trigger_count >= 3:
            return RequirementComplexity.CROSS_REFERENCED
        elif "sub-" in text_lower or "includes but not limited to" in text_lower:
            return RequirementComplexity.NESTED
        else:
            return RequirementComplexity.SIMPLE
    
    @classmethod
    def parse_compound_requirement(cls, requirement_text: str, base_req_id: str) -> List[RequirementFragment]:
        """
        Parse a compound requirement paragraph into individual fragments.
        
        Args:
            requirement_text: The compound requirement text
            base_req_id: Base requirement ID (e.g., "REQ-001")
            
        Returns:
            List of individual requirement fragments
        """
        fragments = []
        
        # Split on common sentence boundaries while preserving context
        import re
        
        # Enhanced sentence splitting that respects requirement boundaries
        sentences = re.split(r'(?<=[.!?])\s+(?=The\s+(?:offeror|contractor|methodology|approach))', requirement_text)
        
        fragment_letter = 'A'
        for i, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # Check if this sentence contains requirement language
            sentence_lower = sentence.lower()
            has_requirement = any(trigger in sentence_lower for trigger in cls.REQUIREMENT_TRIGGERS[:10])  # Use top triggers
            
            if has_requirement and len(sentence) > 50:  # Substantial requirement
                # Extract key phrases for this fragment
                key_phrases = [trigger for trigger in cls.REQUIREMENT_TRIGGERS if trigger in sentence_lower]
                
                # Determine compliance type from language
                compliance_type = ComplianceType.MANDATORY
                if any(word in sentence_lower for word in ["should", "preferred", "desired"]):
                    compliance_type = ComplianceType.DESIRED
                elif any(word in sentence_lower for word in ["may", "can", "optional"]):
                    compliance_type = ComplianceType.OPTIONAL
                
                fragment = RequirementFragment(
                    fragment_id=f"{base_req_id}-{fragment_letter}",
                    parent_req_id=base_req_id,
                    description=sentence,
                    compliance_type=compliance_type,
                    key_phrases=key_phrases[:3]  # Top 3 key phrases
                )
                
                fragments.append(fragment)
                fragment_letter = chr(ord(fragment_letter) + 1)
        
        # If we didn't find clear fragments, create thematic fragments
        if len(fragments) == 0:
            fragments = cls._create_thematic_fragments(requirement_text, base_req_id)
        
        return fragments
    
    @classmethod
    def _create_thematic_fragments(cls, requirement_text: str, base_req_id: str) -> List[RequirementFragment]:
        """
        Create thematic fragments when sentence-based parsing fails.
        
        Uses domain knowledge about common federal requirement themes.
        """
        fragments = []
        text_lower = requirement_text.lower()
        
        # Define thematic patterns
        themes = {
            "methodology": ["methodology", "approach", "method", "procedures"],
            "performance": ["performance", "achieve", "accomplish", "meet"],
            "understanding": ["understanding", "understand", "demonstrates knowledge"],
            "compliance": ["comply", "adhere", "conform", "limits of liability"],
            "maintenance": ["maintenance", "repair", "testing", "inspection"],
            "supply_chain": ["supply chain", "materials", "equipment", "delivery"],
            "standards": ["standards", "industry practices", "specifications"]
        }
        
        fragment_letter = 'A'
        for theme_name, keywords in themes.items():
            if any(keyword in text_lower for keyword in keywords):
                # Extract sentences related to this theme
                theme_sentences = []
                for sentence in requirement_text.split('.'):
                    if any(keyword in sentence.lower() for keyword in keywords):
                        theme_sentences.append(sentence.strip())
                
                if theme_sentences:
                    fragment_text = '. '.join(theme_sentences) + '.'
                    
                    fragment = RequirementFragment(
                        fragment_id=f"{base_req_id}-{fragment_letter}",
                        parent_req_id=base_req_id,
                        description=fragment_text,
                        compliance_type=ComplianceType.MANDATORY,
                        key_phrases=[theme_name.replace('_', ' ')]
                    )
                    
                    fragments.append(fragment)
                    fragment_letter = chr(ord(fragment_letter) + 1)
        
        return fragments
    """
    Examples of custom evaluation criteria found in federal RFPs.
    
    This helps the system learn to recognize and properly categorize
    non-standard evaluation factors.
    """
    
    COMMON_CUSTOM_FACTORS = {
        # Compensation and Benefits
        "total_compensation": {
            "names": ["Total Compensation", "Compensation Package", "Employee Benefits", 
                     "Total Employee Compensation", "Benefit Package"],
            "description": "Evaluation of proposed employee compensation and benefits",
            "typical_weight": 10.0,
            "category": "other"
        },
        
        # Innovation and Technology
        "innovation_capability": {
            "names": ["Innovation", "Innovation Capability", "Innovative Solutions",
                     "Technology Innovation", "Creative Approach"],
            "description": "Ability to provide innovative solutions and approaches",
            "typical_weight": 15.0,
            "category": "technical_approach"
        },
        
        # Reliability and Quality
        "reliability": {
            "names": ["Reliability", "Service Reliability", "System Reliability",
                     "Operational Reliability", "Quality Assurance"],
            "description": "Demonstrated reliability in service delivery and operations",
            "typical_weight": 20.0,
            "category": "past_performance"
        },
        
        # Sustainability and Environment
        "sustainability": {
            "names": ["Sustainability", "Environmental Impact", "Green Practices",
                     "Environmental Sustainability", "Carbon Footprint"],
            "description": "Environmental considerations and sustainable practices",
            "typical_weight": 5.0,
            "category": "other"
        },
        
        # Cultural and Social Factors
        "cultural_competency": {
            "names": ["Cultural Competency", "Cultural Awareness", "Diversity",
                     "Cultural Sensitivity", "Multicultural Capability"],
            "description": "Understanding and ability to work across cultures",
            "typical_weight": 10.0,
            "category": "other"
        },
        
        # Financial Stability
        "financial_stability": {
            "names": ["Financial Stability", "Financial Capability", "Financial Health",
                     "Business Viability", "Financial Strength"],
            "description": "Contractor's financial stability and business viability",
            "typical_weight": 15.0,
            "category": "corporate_experience"
        }
    }