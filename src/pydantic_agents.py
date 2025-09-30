"""
PydanticAI Agents for Structured RFP Analysis

Implements intelligent agents using PydanticAI for guaranteed structured outputs:
- Requirements extraction with Shipley methodology validation
- Compliance assessment with 4-level Shipley scale  
- Section relationship analysis with cross-referencing
- Universal compatibility across government RFP formats

References:
- PydanticAI documentation for agent patterns
- Shipley Proposal Guide p.50-55 (Requirements Analysis)
- Shipley Capture Guide p.85-90 (Gap Analysis)
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import re

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.ollama import OllamaModel
from pydantic import BaseModel, Field

# Import our structured models
from rfp_models import (
    RFPRequirement, ComplianceAssessment, SectionRelationship, RFPSection,
    RFPAnalysisResult, ComplianceLevel, ComplianceStatus, RequirementType,
    RiskLevel, ValidationResult, ProcessingMetadata
)

logger = logging.getLogger(__name__)

# Agent Context Models
class RFPContext(BaseModel):
    """Context information for RFP analysis agents"""
    rfp_title: str
    solicitation_number: str
    agency: Optional[str] = None
    section_content: str
    section_id: str
    related_sections: List[str] = Field(default_factory=list)
    shipley_mode: bool = True

class RequirementsExtractionInput(BaseModel):
    """Input for requirements extraction agent"""
    content: str = Field(..., description="RFP section content to analyze")
    section_id: str = Field(..., description="Section identifier (A, B, C, etc.)")
    context: Optional[str] = Field(None, description="Additional context or related content")
    focus_areas: List[str] = Field(default_factory=list, description="Specific areas to focus on")

class RequirementsExtractionOutput(BaseModel):
    """Structured output from requirements extraction"""
    requirements: List[RFPRequirement] = Field(..., description="Extracted requirements")
    section_summary: str = Field(..., description="Summary of section content")
    key_themes: List[str] = Field(..., description="Major themes identified")
    shipley_notes: List[str] = Field(..., description="Shipley methodology application notes")
    extraction_confidence: float = Field(..., description="Confidence in extraction quality (0-1)")

# Requirements Extraction Agent
def create_requirements_extraction_agent() -> Agent[RFPContext, RequirementsExtractionOutput]:
    """
    Create PydanticAI agent for structured requirements extraction
    
    Uses Shipley methodology to extract and classify requirements with
    guaranteed structured output and validation.
    """
    
    # Use Ollama model for local processing
    model = OllamaModel('qwen2.5-coder:7b')
    
    agent = Agent(
        model=model,
        result_type=RequirementsExtractionOutput,
        system_prompt="""
        You are an expert federal acquisition analyst specialized in RFP requirements extraction 
        using Shipley Proposal Guide methodology (p.50-55).

        CRITICAL INSTRUCTIONS:
        1. Extract ONLY explicit requirements from the provided RFP content
        2. Classify each requirement using Shipley methodology:
           - Must/Shall: Mandatory requirements (non-negotiable)
           - Should: Important requirements (strong preference)  
           - May: Optional requirements (desirable)
           - Will: Government commitments (not contractor requirements)

        3. Categorize requirements by type:
           - functional: What the system must do
           - performance: How well it must perform
           - interface: How it connects/communicates
           - design: Specific design constraints
           - security: Security and compliance requirements
           - technical: Technical specifications
           - management: Project management requirements
           - quality: Quality assurance requirements
           - administrative: Administrative/reporting requirements

        4. Generate requirement IDs in format: REQ-[SECTION]-[###]
           Examples: REQ-L-001, REQ-M-002, REQ-C-015

        5. Extract exact verbatim text for requirement_text field
        6. Include page references when available
        7. Identify keywords for searchability
        8. Note dependencies between requirements

        QUALITY STANDARDS:
        - Focus on contractor obligations, not government commitments
        - Distinguish between requirements and background information
        - Identify measurable/verifiable criteria
        - Flag conflicting or ambiguous requirements
        - Reference specific Shipley Guide pages when applicable

        Provide high-quality extraction following Shipley standards for proposal development.
        """,
    )
    
    @agent.tool
    async def analyze_requirement_pattern(ctx: RunContext[RFPContext], text: str) -> str:
        """Analyze text for requirement patterns and compliance levels"""
        # Requirement indicator patterns
        must_patterns = [r'\bshall\b', r'\bmust\b', r'\brequired\b', r'\bmandatory\b']
        should_patterns = [r'\bshould\b', r'\bwill\b', r'\bpreferred\b']
        may_patterns = [r'\bmay\b', r'\bcould\b', r'\boptional\b', r'\bdesirable\b']
        
        text_lower = text.lower()
        
        # Check for requirement indicators
        has_must = any(re.search(pattern, text_lower) for pattern in must_patterns)
        has_should = any(re.search(pattern, text_lower) for pattern in should_patterns)
        has_may = any(re.search(pattern, text_lower) for pattern in may_patterns)
        
        if has_must:
            return "Must"
        elif has_should:
            return "Should"  
        elif has_may:
            return "May"
        else:
            return "Informational"
    
    @agent.tool
    async def extract_keywords(ctx: RunContext[RFPContext], requirement_text: str) -> List[str]:
        """Extract key terms from requirement text for searchability"""
        # Remove common words and extract meaningful terms
        common_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'shall', 'must', 'will', 'should', 'may'}
        
        # Extract words, filter common terms, keep significant ones
        words = re.findall(r'\b[a-zA-Z]{3,}\b', requirement_text.lower())
        keywords = [word for word in words if word not in common_words]
        
        # Return top 5 most relevant keywords
        return list(set(keywords))[:5]
    
    return agent

# Compliance Assessment Agent
def create_compliance_assessment_agent() -> Agent[RFPContext, ComplianceAssessment]:
    """
    Create PydanticAI agent for Shipley methodology compliance assessment
    
    Evaluates proposal responses against RFP requirements using the
    Shipley 4-level compliance scale with gap analysis.
    """
    
    model = OllamaModel('qwen2.5-coder:7b')
    
    agent = Agent(
        model=model,
        result_type=ComplianceAssessment,
        system_prompt="""
        You are a compliance assessment specialist using Shipley Proposal Guide methodology (p.53-55).

        SHIPLEY 4-LEVEL COMPLIANCE ASSESSMENT:
        - Compliant: Fully meets requirement with proven capability
        - Partial: Meets most aspects but has minor gaps or needs enhancement  
        - Non-Compliant: Cannot meet requirement without significant changes
        - Not Addressed: Requirement not covered in current approach

        ASSESSMENT PROCESS:
        1. Compare requirement against proposal capability/approach
        2. Identify specific evidence of compliance in proposal
        3. Conduct gap analysis per Shipley Capture Guide (p.85-90)
        4. Assess risk level: High/Medium/Low
        5. Develop mitigation strategies for gaps
        6. Identify competitive advantage opportunities
        7. Align with win theme development

        RISK ASSESSMENT CRITERIA:
        - High: Critical to mission, high evaluation weight, difficult to address
        - Medium: Important but manageable, moderate evaluation impact
        - Low: Minor impact, easily mitigated, low evaluation weight

        OUTPUT REQUIREMENTS:
        - Reference specific proposal sections where requirement is addressed
        - Provide detailed gap analysis for non-compliant items
        - Include actionable recommendations
        - Identify win theme opportunities
        - Reference Shipley methodology appropriately

        Maintain objectivity while identifying competitive positioning opportunities.
        """,
    )
    
    @agent.tool
    async def assess_evidence_strength(ctx: RunContext[RFPContext], evidence: str) -> str:
        """Assess the strength of compliance evidence"""
        if not evidence or evidence.strip() == "":
            return "No evidence provided"
        
        # Check for strong evidence indicators
        strong_indicators = ['demonstrated', 'proven', 'certified', 'experienced', 'successfully completed']
        weak_indicators = ['plan to', 'intend to', 'will develop', 'propose to']
        
        evidence_lower = evidence.lower()
        
        if any(indicator in evidence_lower for indicator in strong_indicators):
            return "Strong evidence"
        elif any(indicator in evidence_lower for indicator in weak_indicators):
            return "Weak evidence - needs strengthening"
        else:
            return "Moderate evidence"
    
    @agent.tool  
    async def generate_win_theme_opportunity(ctx: RunContext[RFPContext], requirement: str, capability: str) -> str:
        """Identify potential win theme based on requirement and capability alignment"""
        # Simple pattern matching for win theme identification
        if 'performance' in requirement.lower() and 'exceed' in capability.lower():
            return "Performance Excellence - exceeding baseline requirements"
        elif 'security' in requirement.lower() and 'certified' in capability.lower():
            return "Security Leadership - proven compliance and certification"
        elif 'experience' in requirement.lower() and 'years' in capability.lower():
            return "Proven Experience - extensive relevant background"
        else:
            return "Capability Strength - aligned with requirement"
    
    return agent

# Section Relationship Agent
def create_section_relationship_agent() -> Agent[RFPContext, List[SectionRelationship]]:
    """
    Create PydanticAI agent for analyzing section relationships
    
    Identifies and validates critical connections like L↔M (Instructions ↔ Evaluation)
    and cross-section dependencies for comprehensive RFP understanding.
    """
    
    model = OllamaModel('qwen2.5-coder:7b')
    
    agent = Agent(
        model=model,
        result_type=List[SectionRelationship],
        system_prompt="""
        You are an RFP structure analyst specialized in identifying section relationships 
        critical for proposal development strategy.

        CRITICAL RELATIONSHIPS TO IDENTIFY:

        1. L↔M CONNECTIONS (Most Important):
           - Section L instructions → Section M evaluation factors
           - Page limits in L → Evaluation weights in M
           - Submission requirements in L → Assessment criteria in M

        2. SECTION I CLAUSE APPLICATIONS:
           - Contract clauses → Applicable sections (A-H)
           - FAR/DFARS references → Technical requirements
           - Compliance mandates → Performance sections

        3. SECTION C DEPENDENCIES:
           - Statement of Work → CLINs in Section B
           - Technical requirements → Performance in Section F
           - Deliverables → Evaluation in Section M

        4. J ATTACHMENT SUPPORT:
           - Attachments → Main sections they support
           - Technical data → SOW requirements
           - Forms → Submission instructions

        RELATIONSHIP TYPES:
        - references: One section mentions/cites another
        - depends_on: One section requires another for context
        - evaluates: Section M evaluates content from other sections
        - supports: Attachments/clauses support main sections
        - requires: Mandatory connections for compliance

        IMPORTANCE LEVELS:
        - critical: Essential for proposal success (L↔M connections)
        - important: Significant impact on strategy
        - informational: Helpful context but not critical

        Provide specific examples and clear descriptions of each relationship identified.
        """,
    )
    
    @agent.tool
    async def identify_lm_connections(ctx: RunContext[RFPContext], l_content: str, m_content: str) -> List[str]:
        """Identify specific L↔M connections between instructions and evaluation"""
        connections = []
        
        # Look for common L↔M patterns
        if 'page limit' in l_content.lower() and ('technical' in m_content.lower() or 'management' in m_content.lower()):
            connections.append("Page limits in Section L correspond to evaluation factors in Section M")
        
        if 'format' in l_content.lower() and 'evaluation' in m_content.lower():
            connections.append("Submission format requirements in L align with evaluation methodology in M")
        
        if 'volume' in l_content.lower() and 'factor' in m_content.lower():
            connections.append("Volume organization in L matches evaluation factor structure in M")
        
        return connections
    
    @agent.tool
    async def assess_relationship_criticality(ctx: RunContext[RFPContext], source: str, target: str, description: str) -> str:
        """Assess the criticality of a section relationship"""
        # L↔M relationships are always critical
        if (source == "L" and target == "M") or (source == "M" and target == "L"):
            return "critical"
        
        # Section I clause relationships are important
        if source == "I" or target == "I":
            return "important"
        
        # Section C dependencies are important
        if source == "C" and target in ["B", "F", "M"]:
            return "important"
        
        # J attachment relationships are typically informational
        if source.startswith("J") or target.startswith("J"):
            return "informational"
        
        return "important"
    
    return agent

# Agent Factory and Management
class RFPAnalysisAgents:
    """
    Factory and management class for all RFP analysis PydanticAI agents
    
    Provides centralized access to structured RFP analysis capabilities
    with consistent configuration and error handling.
    """
    
    def __init__(self, ollama_host: str = "localhost", ollama_port: int = 11434):
        """Initialize agents with Ollama configuration"""
        self.ollama_host = ollama_host
        self.ollama_port = ollama_port
        
        # Initialize agents
        self.requirements_agent = create_requirements_extraction_agent()
        self.compliance_agent = create_compliance_assessment_agent() 
        self.relationships_agent = create_section_relationship_agent()
        
        logger.info("PydanticAI agents initialized successfully")
    
    async def extract_requirements(self, content: str, section_id: str, context: Optional[str] = None) -> RequirementsExtractionOutput:
        """Extract structured requirements using PydanticAI agent"""
        try:
            rfp_context = RFPContext(
                rfp_title="RFP Analysis",
                solicitation_number="AUTO-DETECT",
                section_content=content,
                section_id=section_id
            )
            
            # Use the requirements extraction agent
            result = await self.requirements_agent.run(
                user_prompt=f"""
                Extract all requirements from this RFP Section {section_id} content.
                Apply Shipley methodology for classification and structure.
                
                Content to analyze:
                {content}
                
                Additional context: {context or 'None provided'}
                """,
                ctx=rfp_context
            )
            
            return result.data
            
        except Exception as e:
            logger.error(f"Requirements extraction failed: {e}")
            # Return minimal valid structure on error
            return RequirementsExtractionOutput(
                requirements=[],
                section_summary=f"Error processing Section {section_id}: {str(e)}",
                key_themes=[],
                shipley_notes=[f"Processing error: {str(e)}"],
                extraction_confidence=0.0
            )
    
    async def assess_compliance(self, requirement: RFPRequirement, proposal_content: str) -> ComplianceAssessment:
        """Assess compliance using Shipley methodology"""
        try:
            rfp_context = RFPContext(
                rfp_title="Compliance Assessment",
                solicitation_number="AUTO-DETECT",
                section_content=proposal_content,
                section_id=requirement.section_id
            )
            
            result = await self.compliance_agent.run(
                user_prompt=f"""
                Assess compliance for this requirement using Shipley 4-level scale:
                
                Requirement ID: {requirement.requirement_id}
                Requirement Text: {requirement.requirement_text}
                Section: {requirement.section_id}
                Compliance Level: {requirement.compliance_level.value}
                Type: {requirement.requirement_type.value}
                
                Proposal Content to Assess:
                {proposal_content}
                
                Provide detailed Shipley methodology assessment with gap analysis.
                """,
                ctx=rfp_context
            )
            
            return result.data
            
        except Exception as e:
            logger.error(f"Compliance assessment failed: {e}")
            # Return minimal valid assessment on error
            return ComplianceAssessment(
                requirement_id=requirement.requirement_id,
                requirement_text=requirement.requirement_text,
                compliance_status=ComplianceStatus.NOT_ADDRESSED,
                risk_level=RiskLevel.HIGH,
                gap_description=f"Assessment error: {str(e)}",
                recommendations=[f"Retry assessment - error: {str(e)}"]
            )
    
    async def analyze_relationships(self, sections: Dict[str, str]) -> List[SectionRelationship]:
        """Analyze section relationships for comprehensive understanding"""
        try:
            # Create context with all sections
            combined_content = "\n\n".join([f"=== SECTION {sid} ===\n{content}" for sid, content in sections.items()])
            
            rfp_context = RFPContext(
                rfp_title="Section Relationships",
                solicitation_number="AUTO-DETECT",
                section_content=combined_content,
                section_id="ALL",
                related_sections=list(sections.keys())
            )
            
            result = await self.relationships_agent.run(
                user_prompt=f"""
                Analyze relationships between these RFP sections:
                {list(sections.keys())}
                
                Focus on critical connections like:
                - L↔M (Instructions ↔ Evaluation)
                - Section I clause applications
                - Section C dependencies
                - J attachment support
                
                Content provided for analysis:
                {combined_content[:2000]}...  # Truncated for prompt efficiency
                
                Identify specific, actionable relationships with examples.
                """,
                ctx=rfp_context
            )
            
            return result.data
            
        except Exception as e:
            logger.error(f"Relationship analysis failed: {e}")
            return []

# Export the main class for use
__all__ = ['RFPAnalysisAgents', 'RequirementsExtractionOutput', 'RFPContext']