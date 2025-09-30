"""
Enhanced RFP Processing with PydanticAI Integration

Combines section-aware chunking with structured PydanticAI agents for
guaranteed structured outputs and Shipley methodology compliance.

This integration provides:
- Type-safe requirements extraction from RFP sections
- Validated compliance assessments with gap analysis
- Section relationship modeling with L↔M connections
- Universal compatibility across government RFP formats
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import json

from lightrag import LightRAG
from lightrag.utils import logger as lightrag_logger

# Import our components
from rfp_chunking import ShipleyRFPChunker, ContextualChunk
from pydantic_agents import RFPAnalysisAgents, RequirementsExtractionOutput, RFPContext
from rfp_models import (
    RFPRequirement, ComplianceAssessment, SectionRelationship, RFPSection,
    RFPAnalysisResult, ValidationResult, ProcessingMetadata,
    ComplianceLevel, RequirementType
)

logger = logging.getLogger(__name__)

class EnhancedRFPProcessor:
    """
    Advanced RFP processor combining enhanced chunking with PydanticAI agents
    
    Provides end-to-end structured RFP analysis with Shipley methodology
    integration and guaranteed type-safe outputs.
    """
    
    def __init__(self, lightrag_instance: LightRAG):
        """Initialize with LightRAG instance and PydanticAI agents"""
        self.lightrag = lightrag_instance
        self.chunker = ShipleyRFPChunker()
        self.agents = RFPAnalysisAgents()
        
        # Processing state
        self.current_chunks: List[ContextualChunk] = []
        self.current_analysis: Optional[RFPAnalysisResult] = None
        
        logger.info("Enhanced RFP processor initialized with PydanticAI agents")
    
    async def process_rfp_document(self, document_text: str, file_path: Optional[str] = None) -> RFPAnalysisResult:
        """
        Complete RFP processing with structured output
        
        Combines enhanced chunking, PydanticAI analysis, and LightRAG integration
        for comprehensive structured RFP analysis.
        """
        try:
            processing_start = asyncio.get_event_loop().time()
            
            logger.info(f"Starting enhanced RFP processing for: {file_path or 'document'}")
            
            # Step 1: Enhanced section-aware chunking
            self.current_chunks = self.chunker.process_document(document_text)
            section_summary = self.chunker.get_section_summary(self.current_chunks)
            
            logger.info(f"Enhanced chunking complete: {len(self.current_chunks)} chunks, {section_summary['total_sections']} sections")
            
            # Step 2: Extract metadata
            rfp_metadata = self._extract_rfp_metadata(document_text, file_path)
            
            # Step 3: Process sections with PydanticAI agents
            sections_analysis = await self._analyze_sections_with_agents()
            
            # Step 4: Analyze section relationships
            section_relationships = await self._analyze_section_relationships()
            
            # Step 5: Generate comprehensive analysis result
            processing_time = asyncio.get_event_loop().time() - processing_start
            
            self.current_analysis = RFPAnalysisResult(
                rfp_title=rfp_metadata.get("title", "RFP Analysis"),
                solicitation_number=rfp_metadata.get("solicitation_number", "AUTO-DETECTED"),
                agency=rfp_metadata.get("agency", None),
                sections=sections_analysis,
                total_sections=len(sections_analysis),
                sections_with_requirements=sum(1 for s in sections_analysis if s.requirements_count > 0),
                total_requirements=sum(s.requirements_count for s in sections_analysis),
                requirements_by_level=self._calculate_requirements_by_level(sections_analysis),
                requirements_by_type=self._calculate_requirements_by_type(sections_analysis),
                section_relationships=section_relationships,
                critical_relationships=self._identify_critical_relationships(section_relationships),
                analysis_quality_score=self._calculate_quality_score(sections_analysis),
                shipley_references=[
                    "Shipley Proposal Guide p.50-55 (Requirements Analysis)",
                    "Shipley Proposal Guide p.53-55 (Compliance Matrix)",
                    "Shipley Capture Guide p.85-90 (Gap Analysis)",
                    "Enhanced RFP Chunking with PydanticAI Validation"
                ],
                methodology_notes=[
                    f"Processed {len(self.current_chunks)} contextual chunks",
                    f"Section-aware chunking with relationship preservation",
                    f"PydanticAI structured extraction with validation",
                    f"Processing time: {processing_time:.2f} seconds"
                ]
            )
            
            # Step 6: Process through LightRAG for knowledge graph enhancement
            await self._enhance_with_lightrag()
            
            logger.info(f"Enhanced RFP processing complete: {self.current_analysis.total_requirements} requirements, {len(section_relationships)} relationships")
            
            return self.current_analysis
            
        except Exception as e:
            logger.error(f"Enhanced RFP processing failed: {e}")
            raise
    
    def _extract_rfp_metadata(self, document_text: str, file_path: Optional[str]) -> Dict[str, Any]:
        """Extract basic RFP metadata from document"""
        metadata = {}
        
        # Try to extract solicitation number
        import re
        
        # Common solicitation number patterns
        solicitation_patterns = [
            r'[A-Z]{1,3}[\d\-]+R[\d\-]+[A-Z\d]*',  # Military format (e.g., N6945025R0003)
            r'[A-Z]{2,4}[\d\-]+[A-Z\d]*',          # General federal format
            r'Solicitation\s+No[\.:]?\s*([A-Z\d\-]+)',  # Explicit solicitation number
        ]
        
        for pattern in solicitation_patterns:
            match = re.search(pattern, document_text[:2000])  # Search first 2000 chars
            if match:
                metadata["solicitation_number"] = match.group(0) if not match.groups() else match.group(1)
                break
        
        # Try to extract agency
        agency_patterns = [
            r'Department of (\w+)',
            r'(\w+) Command',
            r'Naval (\w+)',
            r'Army (\w+)',
            r'Air Force (\w+)'
        ]
        
        for pattern in agency_patterns:
            match = re.search(pattern, document_text[:1000])
            if match:
                metadata["agency"] = match.group(0)
                break
        
        # Extract title from common locations
        title_patterns = [
            r'SUBJECT[:\s]+(.+?)(?:\n|\r)',
            r'Title[:\s]+(.+?)(?:\n|\r)',
            r'Contract for[:\s]+(.+?)(?:\n|\r)'
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, document_text[:1000], re.IGNORECASE)
            if match:
                metadata["title"] = match.group(1).strip()
                break
        
        if not metadata.get("title") and file_path:
            metadata["title"] = Path(file_path).stem
        
        return metadata
    
    async def _analyze_sections_with_agents(self) -> List[RFPSection]:
        """Analyze each section using PydanticAI agents for structured extraction"""
        sections_analysis = []
        
        # Group chunks by section
        sections_content = {}
        for chunk in self.current_chunks:
            section_id = chunk.section_id.split('-')[0]  # Handle J-1, J-2 etc.
            
            if section_id not in sections_content:
                sections_content[section_id] = {
                    "chunks": [],
                    "content": "",
                    "title": chunk.section_title
                }
            
            sections_content[section_id]["chunks"].append(chunk)
            sections_content[section_id]["content"] += chunk.content + "\n\n"
        
        # Process each section with PydanticAI
        for section_id, section_data in sections_content.items():
            try:
                logger.info(f"Processing section {section_id} with PydanticAI agents")
                
                # Extract requirements using PydanticAI agent
                requirements_result = await self.agents.extract_requirements(
                    content=section_data["content"],
                    section_id=section_id,
                    context=f"RFP Section {section_id} analysis"
                )
                
                # Create RFPSection with structured analysis
                section_analysis = RFPSection(
                    section_id=section_id,
                    section_title=section_data["title"],
                    content=section_data["content"][:5000],  # Truncate for storage
                    subsections=list(set(chunk.subsection_id for chunk in section_data["chunks"] if chunk.subsection_id)),
                    page_range=self._calculate_page_range(section_data["chunks"]),
                    word_count=len(section_data["content"].split()),
                    requirements=requirements_result.requirements,
                    requirements_count=len(requirements_result.requirements),
                    critical_requirements_count=sum(1 for req in requirements_result.requirements if req.compliance_level in [ComplianceLevel.MUST]),
                    contains_evaluation_criteria=section_id == "M",
                    contains_instructions=section_id == "L",
                    contains_specifications=section_id in ["C", "H"],
                    analysis_confidence=requirements_result.extraction_confidence
                )
                
                sections_analysis.append(section_analysis)
                
            except Exception as e:
                logger.error(f"Section {section_id} analysis failed: {e}")
                # Create minimal section on error
                sections_analysis.append(RFPSection(
                    section_id=section_id,
                    section_title=section_data["title"],
                    content=section_data["content"][:1000],
                    analysis_confidence=0.0
                ))
        
        return sections_analysis
    
    async def _analyze_section_relationships(self) -> List[SectionRelationship]:
        """Analyze relationships between sections using PydanticAI"""
        try:
            # Create sections content map for relationship analysis
            sections_map = {}
            for chunk in self.current_chunks:
                section_id = chunk.section_id.split('-')[0]
                if section_id not in sections_map:
                    sections_map[section_id] = ""
                sections_map[section_id] += chunk.content[:500] + "\n"  # Sample content
            
            # Use PydanticAI agent for relationship analysis
            relationships = await self.agents.analyze_relationships(sections_map)
            
            return relationships
            
        except Exception as e:
            logger.error(f"Relationship analysis failed: {e}")
            return []
    
    def _calculate_page_range(self, chunks: List[ContextualChunk]) -> Optional[str]:
        """Calculate page range for section"""
        pages = [chunk.page_number for chunk in chunks if chunk.page_number]
        if pages:
            return f"{min(pages)}-{max(pages)}"
        return None
    
    def _calculate_requirements_by_level(self, sections: List[RFPSection]) -> Dict[str, int]:
        """Calculate requirements distribution by compliance level"""
        counts = {"Must": 0, "Should": 0, "May": 0, "Will": 0}
        
        for section in sections:
            for req in section.requirements:
                counts[req.compliance_level.value] += 1
        
        return counts
    
    def _calculate_requirements_by_type(self, sections: List[RFPSection]) -> Dict[str, int]:
        """Calculate requirements distribution by type"""
        counts = {}
        
        for section in sections:
            for req in section.requirements:
                req_type = req.requirement_type.value
                counts[req_type] = counts.get(req_type, 0) + 1
        
        return counts
    
    def _identify_critical_relationships(self, relationships: List[SectionRelationship]) -> List[str]:
        """Identify critical relationships for proposal strategy"""
        critical = []
        
        for rel in relationships:
            if rel.importance == "critical":
                critical.append(f"{rel.source_section}↔{rel.target_section}: {rel.description}")
        
        return critical
    
    def _calculate_quality_score(self, sections: List[RFPSection]) -> float:
        """Calculate overall analysis quality score"""
        if not sections:
            return 0.0
        
        # Weighted average of section confidence scores
        total_weight = 0
        weighted_sum = 0
        
        for section in sections:
            # Weight by content size and requirement count
            weight = len(section.content) + (section.requirements_count * 100)
            weighted_sum += section.analysis_confidence * weight
            total_weight += weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    async def _enhance_with_lightrag(self):
        """Enhance analysis with LightRAG knowledge graph processing"""
        try:
            if not self.current_analysis:
                return
            
            # Create structured summary for LightRAG
            summary_text = f"""
            === RFP ANALYSIS SUMMARY ===
            Solicitation: {self.current_analysis.solicitation_number}
            Title: {self.current_analysis.rfp_title}
            Agency: {self.current_analysis.agency or 'Not specified'}
            
            === SECTIONS ANALYZED ===
            Total Sections: {self.current_analysis.total_sections}
            Sections with Requirements: {self.current_analysis.sections_with_requirements}
            Total Requirements: {self.current_analysis.total_requirements}
            
            === REQUIREMENTS BREAKDOWN ===
            Must/Shall: {self.current_analysis.requirements_by_level.get('Must', 0)}
            Should: {self.current_analysis.requirements_by_level.get('Should', 0)}
            May: {self.current_analysis.requirements_by_level.get('May', 0)}
            
            === CRITICAL RELATIONSHIPS ===
            {chr(10).join(self.current_analysis.critical_relationships)}
            
            === ANALYSIS QUALITY ===
            Quality Score: {self.current_analysis.analysis_quality_score:.2f}/1.0
            Methodology: Enhanced chunking + PydanticAI + Shipley methodology
            """
            
            # Insert summary into LightRAG
            await self.lightrag.ainsert(summary_text)
            
            logger.info("Analysis enhanced with LightRAG knowledge graph")
            
        except Exception as e:
            logger.warning(f"LightRAG enhancement failed: {e}")
    
    async def query_structured_analysis(self, query: str, section_filter: Optional[str] = None) -> Dict[str, Any]:
        """Query the structured analysis with optional section filtering"""
        if not self.current_analysis:
            return {"error": "No analysis available. Process an RFP document first."}
        
        try:
            # Filter by section if requested
            relevant_sections = self.current_analysis.sections
            if section_filter:
                relevant_sections = [s for s in relevant_sections if s.section_id == section_filter]
            
            # Compile relevant information
            response = {
                "query": query,
                "section_filter": section_filter,
                "document_info": {
                    "solicitation": self.current_analysis.solicitation_number,
                    "title": self.current_analysis.rfp_title,
                    "agency": self.current_analysis.agency
                },
                "sections_analyzed": len(relevant_sections),
                "relevant_requirements": [],
                "section_relationships": [],
                "analysis_metadata": {
                    "total_requirements": self.current_analysis.total_requirements,
                    "quality_score": self.current_analysis.analysis_quality_score,
                    "processing_method": "Enhanced chunking + PydanticAI"
                }
            }
            
            # Extract relevant requirements
            for section in relevant_sections:
                for req in section.requirements:
                    if query.lower() in req.requirement_text.lower() or query.lower() in ' '.join(req.keywords).lower():
                        response["relevant_requirements"].append({
                            "requirement_id": req.requirement_id,
                            "text": req.requirement_text,
                            "section": req.section_id,
                            "compliance_level": req.compliance_level.value,
                            "type": req.requirement_type.value,
                            "keywords": req.keywords
                        })
            
            # Include relevant relationships
            for rel in self.current_analysis.section_relationships:
                if (section_filter and (rel.source_section == section_filter or rel.target_section == section_filter)) or not section_filter:
                    response["section_relationships"].append({
                        "source": rel.source_section,
                        "target": rel.target_section,
                        "type": rel.relationship_type,
                        "description": rel.description,
                        "importance": rel.importance
                    })
            
            return response
            
        except Exception as e:
            logger.error(f"Structured analysis query failed: {e}")
            return {"error": f"Query failed: {str(e)}"}

# Export main class
__all__ = ['EnhancedRFPProcessor']