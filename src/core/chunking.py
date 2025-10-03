"""
RFP-Aware Chunking Strategy for LightRAG Integration

Implements intelligent chunking that preserves RFP section structure and relationships:
- Section A-M identification and preservation
- J attachment context maintenance  
- Cross-section relationship mapping (L↔M, Section I clauses)
- Shipley methodology alignment

References:
- Shipley Proposal Guide p.45-55 for section structure
- Government RFP format standards (FAR 15.210)
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import json
import time

# Performance monitoring
from src.utils.performance_monitor import get_monitor

logger = logging.getLogger(__name__)

@dataclass
class RFPSection:
    """Represents an identified RFP section with context"""
    section_id: str  # "A", "B", "C", "L", "M", "J-1", etc.
    section_title: str
    content: str
    start_pos: int
    end_pos: int
    subsections: List['RFPSubsection'] = None
    page_number: Optional[int] = None
    
    def __post_init__(self):
        if self.subsections is None:
            self.subsections = []

@dataclass 
class RFPSubsection:
    """Represents subsections within major sections"""
    subsection_id: str  # "C.3.1", "L.2.5", "M.1.a", etc.
    title: str
    content: str
    parent_section: str
    start_pos: int
    end_pos: int

@dataclass
class ContextualChunk:
    """Enhanced chunk with RFP section context and relationships"""
    chunk_id: str
    content: str
    section_id: str
    section_title: str
    subsection_id: Optional[str] = None
    chunk_order: int = 0
    relationships: List[str] = None  # Related section IDs
    requirements: List[str] = None   # Identified requirements
    page_number: Optional[int] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.relationships is None:
            self.relationships = []
        if self.requirements is None:
            self.requirements = []
        if self.metadata is None:
            self.metadata = {}

class ShipleyRFPChunker:
    """
    Advanced RFP chunking strategy following Shipley methodology
    
    Preserves government RFP structure and critical section relationships
    for optimal proposal development and compliance analysis.
    """
    
    def __init__(self):
        self.section_patterns = self._build_section_patterns()
        self.relationship_mappings = self._build_relationship_mappings()
        self.requirement_patterns = self._build_requirement_patterns()
        
    def _build_section_patterns(self) -> Dict[str, Dict[str, str]]:
        """Build regex patterns for identifying RFP sections"""
        return {
            # Main RFP Sections (A-M standard)
            "A": {
                "pattern": r"(?i)section\s+a[\s\-:]+(?:solicitation[\/\s]contract\s+form|solicitation|contract\s+form)",
                "title": "Solicitation/Contract Form",
                "alt_patterns": [r"(?i)^a[\.\s\-]+solicitation", r"(?i)part\s+i\s*[\-\s]*section\s+a"]
            },
            "B": {
                "pattern": r"(?i)section\s+b[\s\-:]+(?:supplies?\s+(?:or\s+)?services?|contract\s+schedule)",
                "title": "Supplies or Services and Prices/Costs",
                "alt_patterns": [r"(?i)^b[\.\s\-]+supplies", r"(?i)contract\s+line\s+item(?:s)?\s+(?:\(clin\)|number)"]
            },
            "C": {
                "pattern": r"(?i)section\s+c[\s\-:]+(?:statement\s+of\s+work|description|sow|specifications)",
                "title": "Statement of Work",
                "alt_patterns": [r"(?i)^c[\.\s\-]+statement\s+of\s+work", r"(?i)performance\s+work\s+statement"]
            },
            "D": {
                "pattern": r"(?i)section\s+d[\s\-:]+(?:packaging\s+and\s+marking|packaging|marking)",
                "title": "Packaging and Marking",
                "alt_patterns": [r"(?i)^d[\.\s\-]+packaging"]
            },
            "E": {
                "pattern": r"(?i)section\s+e[\s\-:]+(?:inspection\s+and\s+acceptance|inspection|acceptance)",
                "title": "Inspection and Acceptance",
                "alt_patterns": [r"(?i)^e[\.\s\-]+inspection"]
            },
            "F": {
                "pattern": r"(?i)section\s+f[\s\-:]+(?:deliveries?\s+(?:or\s+)?performance|performance|delivery)",
                "title": "Deliveries or Performance",
                "alt_patterns": [r"(?i)^f[\.\s\-]+deliver", r"(?i)period\s+of\s+performance"]
            },
            "G": {
                "pattern": r"(?i)section\s+g[\s\-:]+(?:contract\s+administration\s+data|administration|admin)",
                "title": "Contract Administration Data",
                "alt_patterns": [r"(?i)^g[\.\s\-]+contract\s+administration"]
            },
            "H": {
                "pattern": r"(?i)section\s+h[\s\-:]+(?:special\s+contract\s+requirements|special|requirements)",
                "title": "Special Contract Requirements",
                "alt_patterns": [r"(?i)^h[\.\s\-]+special"]
            },
            "I": {
                "pattern": r"(?i)section\s+i[\s\-:]+(?:contract\s+clauses|clauses)",
                "title": "Contract Clauses",
                "alt_patterns": [r"(?i)^i[\.\s\-]+contract\s+clauses", r"(?i)applicable\s+clauses"]
            },
            "J": {
                "pattern": r"(?i)section\s+j[\s\-:]+(?:list\s+of\s+(?:attachments|documents)|attachments|documents)",
                "title": "List of Attachments",
                "alt_patterns": [r"(?i)^j[\.\s\-]+list\s+of", r"(?i)attachment(?:s)?"]
            },
            "K": {
                "pattern": r"(?i)section\s+k[\s\-:]+(?:representations?[,\s]+certifications?|representations?|certifications?)",
                "title": "Representations, Certifications and Other Statements",
                "alt_patterns": [r"(?i)^k[\.\s\-]+representations"]
            },
            "L": {
                "pattern": r"(?i)section\s+l[\s\-:]+(?:instructions?\s+to\s+offerors?|instructions?)",
                "title": "Instructions to Offerors",
                "alt_patterns": [r"(?i)^l[\.\s\-]+instructions", r"(?i)proposal\s+preparation\s+instructions"]
            },
            "M": {
                "pattern": r"(?i)section\s+m[\s\-:]+(?:evaluation\s+factors?|evaluation)",
                "title": "Evaluation Factors for Award",
                "alt_patterns": [r"(?i)^m[\.\s\-]+evaluation", r"(?i)basis\s+for\s+award"]
            },
            
            # J Attachments (common patterns)
            # Universal pattern: Match legitimate attachment designations, not random text fragments
            # Examples: "Attachment J-1", "Exhibit J.2", "Attachment JL-1", but NOT "Attachment Line Item"
            "J_ATTACHMENT": {
                # Primary: "Attachment/Exhibit" followed by "J" + delimiter + alphanumeric designation
                # Requires explicit delimiter (hyphen, period, or space) to avoid matching random words
                "pattern": r"(?i)(?:attachment|exhibit)\s+j[\-\.\s]([a-z0-9]+(?:[\-\.][a-z0-9]+)*)(?:\s+[\-:]\s*(.+?))?(?:\n|\r|$)",
                "title": "J Attachment",
                "alt_patterns": [
                    # Alt 1: "Section J Attachment" with designation
                    r"(?i)section\s+j\s+attachment\s+([a-z0-9]+(?:[\-\.][a-z0-9]+)*)(?:\s+[\-:]\s*(.+?))?(?:\n|\r|$)",
                    # Alt 2: Standalone "J-" with multi-char designation (prevents matching "J-Line" fragments)
                    r"(?i)\bj[\-]([a-z0-9]{2,}(?:[\-\.][a-z0-9]+)*)(?:\s+[\-:]\s*(.+?))?(?:\n|\r|$)"
                ]
            }
        }
    
    def _build_relationship_mappings(self) -> Dict[str, List[str]]:
        """Define critical relationships between RFP sections"""
        return {
            # Section L Instructions → Section M Evaluation (critical relationship)
            "L": ["M", "K"],  # Instructions link to evaluation and reps/certs
            "M": ["L", "C"],  # Evaluation links back to instructions and SOW
            
            # Section C SOW → Multiple sections
            "C": ["B", "F", "H", "M"],  # SOW links to CLINs, performance, special reqs, evaluation
            
            # Section I Clauses → All sections (general applicability)
            "I": ["A", "B", "C", "D", "E", "F", "G", "H"],
            
            # Section H Special Requirements → SOW and Evaluation
            "H": ["C", "M", "I"],
            
            # Section F Performance → SOW and CLINs
            "F": ["B", "C"],
            
            # Section B CLINs → SOW and Performance
            "B": ["C", "F"],
            
            # J Attachments → Multiple sections (content dependent)
            "J": ["C", "L", "M", "H"]  # Common attachments reference these
        }
    
    def _build_requirement_patterns(self) -> List[str]:
        """Patterns for identifying requirements within sections"""
        return [
            r"(?i)\b(?:shall|must|will|required?|mandatory)\b",
            r"(?i)\bofferor(?:s)?\s+(?:shall|must|will)\b",
            r"(?i)\bcontractor(?:s)?\s+(?:shall|must|will)\b",
            r"(?i)\b(?:proposal|response)\s+(?:shall|must|will)\b",
            r"(?i)\bis\s+required\b",
            r"(?i)\bmandatory\s+requirement\b"
        ]
    
    def identify_sections(self, document_text: str) -> List[RFPSection]:
        """
        Identify and extract RFP sections from document text
        
        Returns list of RFPSection objects with content and metadata
        """
        logger.info(f"🔍 Scanning document for RFP sections ({len(document_text):,} chars)...")
        sections = []
        text_length = len(document_text)
        
        # Track all section matches with positions
        section_matches = []
        
        # Search for each section pattern
        for section_id, patterns in self.section_patterns.items():
            if section_id == "J_ATTACHMENT":
                continue  # Handle J attachments separately
            
            logger.info(f"   Searching for Section {section_id}...")
                
            # Try main pattern first
            main_pattern = patterns["pattern"]
            matches = list(re.finditer(main_pattern, document_text, re.MULTILINE))
            
            # Try alternative patterns if no main match
            if not matches and "alt_patterns" in patterns:
                for alt_pattern in patterns["alt_patterns"]:
                    matches = list(re.finditer(alt_pattern, document_text, re.MULTILINE))
                    if matches:
                        break
            
            # Record matches with metadata
            for match in matches:
                section_matches.append({
                    "section_id": section_id,
                    "title": patterns["title"], 
                    "start": match.start(),
                    "end": match.end(),
                    "match_text": match.group(0)
                })
        
        # Handle J attachments separately (they can be numbered)
        j_pattern = self.section_patterns["J_ATTACHMENT"]["pattern"]
        j_matches = list(re.finditer(j_pattern, document_text, re.MULTILINE))
        
        for match in j_matches:
            attachment_num = match.group(1) if match.group(1) else "1"
            attachment_title = match.group(2) if len(match.groups()) > 1 and match.group(2) else "Attachment"
            
            section_matches.append({
                "section_id": f"J-{attachment_num}",
                "title": f"Attachment {attachment_num}: {attachment_title.strip()}",
                "start": match.start(),
                "end": match.end(),
                "match_text": match.group(0)
            })
        
        # Sort sections by position in document
        section_matches.sort(key=lambda x: x["start"])
        
        # Extract content between section boundaries
        for i, section_match in enumerate(section_matches):
            start_pos = section_match["start"]
            
            # Find end position (start of next section or end of document)
            if i + 1 < len(section_matches):
                end_pos = section_matches[i + 1]["start"]
            else:
                end_pos = text_length
            
            # Extract section content
            section_content = document_text[start_pos:end_pos].strip()
            
            # Estimate page number (rough approximation)
            chars_before = len(document_text[:start_pos])
            estimated_page = max(1, chars_before // 2000)  # ~2000 chars per page estimate
            
            # Create RFPSection object
            rfp_section = RFPSection(
                section_id=section_match["section_id"],
                section_title=section_match["title"],
                content=section_content,
                start_pos=start_pos,
                end_pos=end_pos,
                page_number=estimated_page
            )
            
            # Identify subsections within this section
            rfp_section.subsections = self._identify_subsections(section_content, section_match["section_id"])
            
            sections.append(rfp_section)
        
        logger.info(f"Identified {len(sections)} RFP sections: {[s.section_id for s in sections]}")
        return sections
    
    def _identify_subsections(self, section_content: str, parent_section_id: str) -> List[RFPSubsection]:
        """Identify subsections within a major section"""
        subsections = []
        
        # Common subsection patterns
        subsection_patterns = [
            rf"(?i)^{parent_section_id}\.(\d+(?:\.\d+)*)\s+(.+?)(?:\n|\r|$)",  # A.1, A.1.1, etc.
            rf"(?i)^(\d+(?:\.\d+)*)\s+(.+?)(?:\n|\r|$)",  # 1.1, 1.1.1, etc.
            rf"(?i)^{parent_section_id}\.([a-z]+)\s+(.+?)(?:\n|\r|$)",  # A.a, A.b, etc.
            rf"(?i)^\(([a-z\d]+)\)\s+(.+?)(?:\n|\r|$)"  # (a), (1), etc.
        ]
        
        for pattern in subsection_patterns:
            matches = list(re.finditer(pattern, section_content, re.MULTILINE))
            
            for match in matches:
                subsection_num = match.group(1)
                subsection_title = match.group(2).strip() if len(match.groups()) > 1 else ""
                
                subsection_id = f"{parent_section_id}.{subsection_num}"
                
                # Find subsection content (until next subsection or end)
                start_pos = match.start()
                end_pos = len(section_content)  # Default to end of section
                
                # Look for next subsection to determine end
                remaining_matches = [m for m in matches if m.start() > start_pos]
                if remaining_matches:
                    end_pos = remaining_matches[0].start()
                
                subsection_content = section_content[start_pos:end_pos].strip()
                
                if len(subsection_content) > 50:  # Only include substantial subsections
                    subsections.append(RFPSubsection(
                        subsection_id=subsection_id,
                        title=subsection_title,
                        content=subsection_content,
                        parent_section=parent_section_id,
                        start_pos=start_pos,
                        end_pos=end_pos
                    ))
            
            # If we found subsections with this pattern, break
            if subsections:
                break
        
        return subsections
    
    def create_contextual_chunks(self, sections: List[RFPSection], max_chunk_size: int = 2000) -> List[ContextualChunk]:
        """
        Create contextual chunks from identified RFP sections
        
        Preserves section context while maintaining optimal chunk sizes for LightRAG.
        Uses requirement-based splitting for sections with high requirement density.
        """
        chunks = []
        chunk_counter = 0
        
        for section in sections:
            # Determine relationships for this section
            relationships = self.relationship_mappings.get(section.section_id.split('-')[0], [])
            
            # Check if section has high requirement density (>5 requirements)
            requirements = self._extract_requirements(section.content)
            use_requirement_splitting = len(requirements) > 5
            
            if use_requirement_splitting:
                # Use requirement-based splitting for high-density sections
                logger.info(
                    f"🔍 Section {section.section_id} has {len(requirements)} requirements - "
                    f"using requirement-based splitting"
                )
                
                req_chunks = self.split_by_requirements(
                    content=section.content,
                    section_id=section.section_id,
                    section_title=section.section_title,
                    subsection_id=None,
                    max_requirements_per_chunk=3
                )
                
                # Assign chunk IDs and add to main chunks list
                for req_chunk in req_chunks:
                    req_chunk.chunk_id = f"chunk_{chunk_counter:04d}"
                    req_chunk.chunk_order = chunk_counter
                    req_chunk.page_number = section.page_number
                    chunks.append(req_chunk)
                    chunk_counter += 1
                
                continue  # Skip normal processing for this section
            
            # Handle sections by size (existing logic)
            if len(section.content) <= max_chunk_size:
                # Small section - single chunk
                chunk = ContextualChunk(
                    chunk_id=f"chunk_{chunk_counter:04d}",
                    content=section.content,
                    section_id=section.section_id,
                    section_title=section.section_title,
                    chunk_order=chunk_counter,
                    relationships=relationships,
                    page_number=section.page_number,
                    metadata={
                        "section_type": "complete_section",
                        "subsection_count": len(section.subsections),
                        "has_requirements": self._has_requirements(section.content)
                    }
                )
                
                # Identify requirements in this chunk
                chunk.requirements = requirements
                
                chunks.append(chunk)
                chunk_counter += 1
                
            else:
                # Large section - split by subsections or intelligently
                if section.subsections:
                    # Split by subsections
                    for subsection in section.subsections:
                        if len(subsection.content) <= max_chunk_size:
                            chunk = ContextualChunk(
                                chunk_id=f"chunk_{chunk_counter:04d}",
                                content=subsection.content,
                                section_id=section.section_id,
                                section_title=section.section_title,
                                subsection_id=subsection.subsection_id,
                                chunk_order=chunk_counter,
                                relationships=relationships,
                                page_number=section.page_number,
                                metadata={
                                    "section_type": "subsection",
                                    "subsection_title": subsection.title,
                                    "has_requirements": self._has_requirements(subsection.content)
                                }
                            )
                            
                            chunk.requirements = self._extract_requirements(subsection.content)
                            chunks.append(chunk)
                            chunk_counter += 1
                        else:
                            # Very large subsection - split further
                            sub_chunks = self._split_large_content(
                                subsection.content, max_chunk_size, 
                                section.section_id, section.section_title,
                                subsection.subsection_id, relationships,
                                section.page_number
                            )
                            
                            for sub_chunk in sub_chunks:
                                sub_chunk.chunk_id = f"chunk_{chunk_counter:04d}"
                                sub_chunk.chunk_order = chunk_counter
                                chunks.append(sub_chunk)
                                chunk_counter += 1
                
                else:
                    # No subsections - split by paragraphs/logical breaks
                    section_chunks = self._split_large_content(
                        section.content, max_chunk_size,
                        section.section_id, section.section_title,
                        None, relationships, section.page_number
                    )
                    
                    for section_chunk in section_chunks:
                        section_chunk.chunk_id = f"chunk_{chunk_counter:04d}"
                        section_chunk.chunk_order = chunk_counter
                        chunks.append(section_chunk)
                        chunk_counter += 1
        
        logger.info(f"Created {len(chunks)} contextual chunks from {len(sections)} sections")
        return chunks
    
    def _split_large_content(self, content: str, max_size: int, section_id: str, 
                           section_title: str, subsection_id: Optional[str], 
                           relationships: List[str], page_number: Optional[int]) -> List[ContextualChunk]:
        """Split large content into smaller chunks while preserving context"""
        chunks = []
        
        # Try to split by paragraphs first
        paragraphs = re.split(r'\n\s*\n', content)
        
        current_chunk = ""
        chunk_parts = []
        
        for paragraph in paragraphs:
            if len(current_chunk + paragraph) <= max_size:
                current_chunk += paragraph + "\n\n"
                chunk_parts.append(paragraph)
            else:
                # Current chunk is full, save it
                if current_chunk.strip():
                    chunk = ContextualChunk(
                        chunk_id="",  # Will be set by caller
                        content=current_chunk.strip(),
                        section_id=section_id,
                        section_title=section_title,
                        subsection_id=subsection_id,
                        chunk_order=0,  # Will be set by caller
                        relationships=relationships,
                        page_number=page_number,
                        metadata={
                            "section_type": "partial_section",
                            "paragraph_count": len(chunk_parts),
                            "has_requirements": self._has_requirements(current_chunk)
                        }
                    )
                    
                    chunk.requirements = self._extract_requirements(current_chunk)
                    chunks.append(chunk)
                
                # Start new chunk
                current_chunk = paragraph + "\n\n"
                chunk_parts = [paragraph]
        
        # Add final chunk if there's remaining content
        if current_chunk.strip():
            chunk = ContextualChunk(
                chunk_id="",
                content=current_chunk.strip(),
                section_id=section_id,
                section_title=section_title,
                subsection_id=subsection_id,
                chunk_order=0,
                relationships=relationships,
                page_number=page_number,
                metadata={
                    "section_type": "partial_section",
                    "paragraph_count": len(chunk_parts),
                    "has_requirements": self._has_requirements(current_chunk)
                }
            )
            
            chunk.requirements = self._extract_requirements(current_chunk)
            chunks.append(chunk)
        
        return chunks
    
    def _has_requirements(self, text: str) -> bool:
        """Check if text contains requirement patterns"""
        for pattern in self.requirement_patterns:
            if re.search(pattern, text):
                return True
        return False
    
    def _extract_requirements(self, text: str) -> List[str]:
        """Extract requirement statements from text"""
        requirements = []
        
        # Split into sentences and check each for requirement patterns
        sentences = re.split(r'[.!?]+', text)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:  # Skip very short fragments
                continue
                
            # Check if sentence contains requirement indicators
            for pattern in self.requirement_patterns:
                if re.search(pattern, sentence):
                    # Clean up and add requirement
                    clean_req = re.sub(r'\s+', ' ', sentence).strip()
                    if clean_req and len(clean_req) > 30:  # Substantial requirement
                        requirements.append(clean_req)
                    break
        
        return requirements[:10]  # Limit to top 10 requirements per chunk
    
    def split_by_requirements(
        self, 
        content: str, 
        section_id: str,
        section_title: str,
        subsection_id: Optional[str] = None,
        max_requirements_per_chunk: int = 3
    ) -> List[ContextualChunk]:
        """
        Split content by requirements to prevent timeout and truncation issues.
        
        When a section contains >5 requirements, split it into smaller chunks
        with max 3 requirements each. Maintains section context across splits.
        
        This prevents:
        - LLM timeout on requirement-heavy sections
        - Token truncation losing critical requirements
        - O(n²) relationship explosion from large requirement sets
        
        Args:
            content: Section content to split
            section_id: Section identifier
            section_title: Section title
            subsection_id: Optional subsection identifier
            max_requirements_per_chunk: Maximum requirements per chunk (default: 3)
        
        Returns:
            List of ContextualChunk objects with balanced requirement distribution
        """
        # Extract all requirements from content
        all_requirements = self._extract_requirements(content)
        
        # If 5 or fewer requirements, return single chunk (no splitting needed)
        if len(all_requirements) <= 5:
            return []  # Caller will handle as normal chunk
        
        logger.info(
            f"⚠️ Section {section_id} has {len(all_requirements)} requirements - "
            f"splitting into chunks with max {max_requirements_per_chunk} requirements each"
        )
        
        # Split content by locating requirement positions
        chunks = []
        requirement_positions = []
        
        # Find position of each requirement in content
        for req in all_requirements:
            # Find first occurrence of requirement text
            pos = content.find(req[:50])  # Match on first 50 chars for safety
            if pos != -1:
                requirement_positions.append((pos, req))
        
        # Sort by position
        requirement_positions.sort(key=lambda x: x[0])
        
        # Group requirements into chunks
        req_groups = []
        current_group = []
        
        for pos, req in requirement_positions:
            current_group.append((pos, req))
            
            if len(current_group) >= max_requirements_per_chunk:
                req_groups.append(current_group)
                current_group = []
        
        # Add remaining requirements
        if current_group:
            req_groups.append(current_group)
        
        # Create chunks based on requirement groups
        for group_idx, req_group in enumerate(req_groups, start=1):
            # Determine chunk boundaries
            start_pos = req_group[0][0]  # Start of first requirement
            
            # Find end position (start of next group or end of content)
            if group_idx < len(req_groups):
                end_pos = req_groups[group_idx][0][0]  # Start of next group's first req
            else:
                end_pos = len(content)  # End of content
            
            # Extract chunk content with some context before first requirement
            context_before = max(0, start_pos - 200)  # Include 200 chars before for context
            chunk_content = content[context_before:end_pos].strip()
            
            # Create chunk
            chunk = ContextualChunk(
                chunk_id="",  # Will be set by caller
                content=chunk_content,
                section_id=section_id,
                section_title=section_title,
                subsection_id=subsection_id,
                chunk_order=0,  # Will be set by caller
                relationships=self.relationship_mappings.get(section_id.split('-')[0], []),
                page_number=None,  # Page estimation handled by caller
                metadata={
                    "section_type": "requirement_split",
                    "split_reason": "high_requirement_density",
                    "requirements_in_chunk": len(req_group),
                    "total_requirements_in_section": len(all_requirements),
                    "chunk_part": f"{group_idx}/{len(req_groups)}",
                    "has_requirements": True
                }
            )
            
            # Add requirements for this chunk
            chunk.requirements = [req for pos, req in req_group]
            
            chunks.append(chunk)
            
            logger.info(
                f"   Created requirement chunk {group_idx}/{len(req_groups)}: "
                f"{len(req_group)} requirements, {len(chunk_content)} chars"
            )
        
        logger.info(
            f"✅ Split section {section_id} into {len(chunks)} requirement-based chunks "
            f"({len(all_requirements)} total requirements)"
        )
        
        return chunks
    
    def process_document(self, document_text: str, max_chunk_size: int = 2000) -> List[ContextualChunk]:
        """
        Main entry point: Process entire RFP document into contextual chunks
        
        Returns list of ContextualChunk objects ready for LightRAG processing
        """
        monitor = get_monitor()
        start_time = time.time()
        
        logger.info("🎯 Starting RFP-aware document chunking")
        logger.info(f"📄 Document size: {len(document_text):,} characters")
        logger.info(f"📦 Target chunk size: {max_chunk_size} tokens")
        
        # Step 1: Identify RFP sections
        logger.info("🔍 Identifying RFP sections...")
        sections = self.identify_sections(document_text)
        logger.info(f"📋 Found {len(sections)} sections: {[s.section_id for s in sections]}")
        
        # Step 2: Create contextual chunks
        logger.info("✂️ Creating contextual chunks...")
        chunks = self.create_contextual_chunks(sections, max_chunk_size)
        logger.info(f"📦 Created {len(chunks)} contextual chunks")
        
        # Step 3: Enhance with cross-references
        logger.info("🔗 Adding cross-references...")
        chunks = self._add_cross_references(chunks)
        
        processing_time = time.time() - start_time
        logger.info(f"✅ RFP chunking complete: {len(chunks)} contextual chunks from {len(sections)} sections")
        logger.info(f"⏱️ Total processing time: {processing_time:.2f}s")
        
        # Log performance summary
        section_summary = self.get_section_summary(chunks)
        logger.info(f"📊 Section summary: {section_summary['total_sections']} sections processed")
        
        return chunks
    
    def _add_cross_references(self, chunks: List[ContextualChunk]) -> List[ContextualChunk]:
        """Add cross-references between related chunks"""
        # Build section index
        section_index = {}
        for chunk in chunks:
            section_id = chunk.section_id.split('-')[0]  # Handle J-1, J-2 etc.
            if section_id not in section_index:
                section_index[section_id] = []
            section_index[section_id].append(chunk.chunk_id)
        
        # Enhance relationships based on actual available sections
        for chunk in chunks:
            base_section = chunk.section_id.split('-')[0]
            
            # Add specific cross-references based on content analysis
            if base_section == "L" and chunk.subsection_id:
                # Section L instructions often reference evaluation factors
                if "evaluat" in chunk.content.lower() and "M" in section_index:
                    chunk.relationships.extend(section_index["M"])
                    
            elif base_section == "M" and chunk.subsection_id:
                # Section M evaluation often references instructions
                if "instruction" in chunk.content.lower() and "L" in section_index:
                    chunk.relationships.extend(section_index["L"])
                    
            elif base_section == "C":
                # SOW often references CLINs and performance requirements
                if "clin" in chunk.content.lower() and "B" in section_index:
                    chunk.relationships.extend(section_index["B"])
                if "performance" in chunk.content.lower() and "F" in section_index:
                    chunk.relationships.extend(section_index["F"])
            
            # Remove duplicates and self-references
            chunk.relationships = list(set(chunk.relationships))
            if chunk.chunk_id in chunk.relationships:
                chunk.relationships.remove(chunk.chunk_id)
        
        return chunks

    def get_section_summary(self, chunks: List[ContextualChunk]) -> Dict[str, Any]:
        """Generate summary of identified sections and their relationships"""
        section_summary = {}
        section_counts = {}
        
        for chunk in chunks:
            section_id = chunk.section_id
            
            if section_id not in section_summary:
                section_summary[section_id] = {
                    "title": chunk.section_title,
                    "chunk_count": 0,
                    "has_requirements": False,
                    "total_content_length": 0,
                    "subsections": set(),
                    "relationships": set()
                }
            
            # Update section data
            section_data = section_summary[section_id]
            section_data["chunk_count"] += 1
            section_data["total_content_length"] += len(chunk.content)
            
            if chunk.requirements:
                section_data["has_requirements"] = True
            
            if chunk.subsection_id:
                section_data["subsections"].add(chunk.subsection_id)
            
            section_data["relationships"].update(chunk.relationships)
        
        # Convert sets to lists for JSON serialization
        for section_data in section_summary.values():
            section_data["subsections"] = list(section_data["subsections"])
            section_data["relationships"] = list(section_data["relationships"])
        
        return {
            "sections_identified": list(section_summary.keys()),
            "total_sections": len(section_summary),
            "total_chunks": sum(data["chunk_count"] for data in section_summary.values()),
            "sections_with_requirements": [sid for sid, data in section_summary.items() if data["has_requirements"]],
            "section_details": section_summary
        }