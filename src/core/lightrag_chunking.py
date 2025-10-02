"""
LightRAG Chunking Extension for RFP-Aware Processing

Provides the proper LightRAG extension point: a custom chunking_func that preserves
RFP section structure and relationships. This is the native way to extend LightRAG
for domain-specific chunking as recommended by the framework.

Usage:
    from src.core.lightrag_chunking import rfp_aware_chunking_func

    rag = LightRAG(
        chunking_func=rfp_aware_chunking_func,
        # ... other params
    )
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from src.core.chunking import ShipleyRFPChunker

logger = logging.getLogger(__name__)

# Global chunk metadata mapping for progress tracking
# Maps chunk_id -> metadata for section visibility during processing
_CHUNK_METADATA_MAP = {}

def rfp_aware_chunking_func(
    tokenizer,
    content: str,
    split_by_character: Optional[str] = None,
    split_by_character_only: bool = False,
    chunk_overlap_token_size: int = 100,
    chunk_token_size: int = 1200,
) -> List[Dict[str, Any]]:
    """
    Custom chunking function for LightRAG that preserves RFP section structure.

    This is LightRAG's proper extension point for domain-specific chunking.
    Automatically detects RFP documents and applies section-aware processing.

    LightRAG calls this function with specific parameters during document processing.
    This signature MUST match LightRAG's expectations exactly.

    Args:
        tokenizer: Tokenizer instance for counting tokens
        content: Document text to chunk
        split_by_character: Optional character to split on
        split_by_character_only: If True, split only on specified character
        chunk_overlap_token_size: Overlap between consecutive chunks
        chunk_token_size: Maximum tokens per chunk

    Returns:
        List of chunk dictionaries in LightRAG format:
        [
            {
                'content': str,  # The chunk text
                'tokens': int,   # Token count
                'metadata': dict  # Optional metadata
            },
            ...
        ]
    """
    try:
        logger.info(f"🔍 Starting chunking - content length: {len(content):,} chars")
        
        # Detect if this is an RFP document FIRST (fast check)
        is_rfp = _detect_rfp_document(content)
        logger.info(f"📋 RFP detection result: {is_rfp}")

        if is_rfp:
            logger.info("🎯 RFP document detected - using enhanced section-aware chunking")
            
            # Initialize RFP chunker
            logger.info("⚙️ Initializing ShipleyRFPChunker...")
            rfp_chunker = ShipleyRFPChunker()
            logger.info("✅ ShipleyRFPChunker initialized")

            # Use enhanced RFP chunking
            logger.info("📊 Processing document with Shipley RFP methodology...")
            rfp_chunks = rfp_chunker.process_document(content)
            logger.info(f"✅ RFP processing complete: {len(rfp_chunks)} chunks generated")

            # Convert to LightRAG format
            lightrag_chunks = []
            for idx, chunk in enumerate(rfp_chunks, start=1):
                # Create enhanced content with section context
                enhanced_content = _create_enhanced_chunk_content(chunk)

                # Create metadata dict
                chunk_metadata = {
                    'chunk_id': chunk.chunk_id,
                    'section_id': chunk.section_id,
                    'section_title': chunk.section_title,
                    'subsection_id': chunk.subsection_id,
                    'chunk_order': chunk.chunk_order,
                    'page_number': chunk.page_number,
                    'relationships': chunk.relationships,
                    'requirements_count': len(chunk.requirements),
                    'has_requirements': len(chunk.requirements) > 0,
                    'rfp_enhanced': True,
                    'document_type': 'rfp',
                    **chunk.metadata
                }
                
                # Store metadata in global map for progress tracking
                # This allows us to log section info when LightRAG processes each chunk
                _CHUNK_METADATA_MAP[chunk.chunk_id] = chunk_metadata
                
                # Log chunk creation with section visibility
                section_info = f"Section {chunk.section_id} - {chunk.section_title}"
                if chunk.subsection_id:
                    section_info += f" ({chunk.subsection_id})"
                logger.info(
                    f"📝 Chunk {idx}/{len(rfp_chunks)}: {section_info}, "
                    f"Page {chunk.page_number}, {len(chunk.requirements)} reqs"
                )

                chunk_dict = {
                    'content': enhanced_content,
                    'metadata': chunk_metadata
                }
                lightrag_chunks.append(chunk_dict)

            logger.info(f"✅ Enhanced chunking: {len(lightrag_chunks)} RFP-aware chunks created")
            logger.info(f"📊 Section distribution:")
            
            # Log section summary
            section_counts = {}
            for chunk in rfp_chunks:
                section_id = chunk.section_id
                section_counts[section_id] = section_counts.get(section_id, 0) + 1
            
            for section_id in sorted(section_counts.keys()):
                count = section_counts[section_id]
                logger.info(f"   Section {section_id}: {count} chunks")
            
            return lightrag_chunks

        else:
            logger.info("📄 Standard document - using default LightRAG chunking")
            # Fall back to standard LightRAG chunking for non-RFP documents
            from lightrag.operate import chunking_by_token_size
            return chunking_by_token_size(
                tokenizer,
                content,
                split_by_character,
                split_by_character_only,
                chunk_overlap_token_size,
                chunk_token_size,
            )

    except Exception as e:
        logger.warning(f"⚠️ Enhanced chunking failed: {e}")
        # Always fall back to standard chunking on error
        from lightrag.operate import chunking_by_token_size
        return chunking_by_token_size(
            tokenizer,
            content,
            split_by_character,
            split_by_character_only,
            chunk_overlap_token_size,
            chunk_token_size,
        )


def _detect_rfp_document(content: str) -> bool:
    """
    Detect if document content appears to be an RFP.

    Uses pattern matching similar to RFPAwareLightRAG but simplified for chunking context.
    """
    content_lower = content.lower()

    # RFP detection patterns
    rfp_patterns = [
        r'solicitation\s+(?:number|no\.?|#)?\s*:?\s*([A-Z0-9\-_]+)',
        r'rfp\s+(?:number|no\.?|#)?\s*:?\s*([A-Z0-9\-_]+)',
        r'request\s+for\s+proposal',
        r'section\s+[A-M]\s*[:\.]',
        r'instructions\s+to\s+offerors',
        r'evaluation\s+factors?\s+for\s+award',
        r'statement\s+of\s+work',
        r'performance\s+work\s+statement',
        r'attachment\s+j-?[0-9]+',
        r'solicitation\s+provisions',
        r'contract\s+clauses',
    ]

    pattern_matches = 0

    # Check content for RFP patterns
    for pattern in rfp_patterns:
        if __import__('re').search(pattern, content_lower):
            pattern_matches += 1

    # Check for section structure (strong indicator)
    section_pattern = r'section\s+[a-m]\s*[\.\:]'
    if __import__('re').search(section_pattern, content_lower):
        pattern_matches += 2  # Weight section patterns more heavily

    # Check for multiple sections
    sections_found = len(__import__('re').findall(r'section\s+[a-m]', content_lower))
    if sections_found >= 3:
        pattern_matches += 3  # Strong indicator of RFP structure

    # Require multiple pattern matches for detection
    return pattern_matches >= 3


def _create_enhanced_chunk_content(chunk) -> str:
    """
    Create enhanced chunk content with minimal inline context.
    
    CRITICAL: Keep content clean for LightRAG's entity extraction.
    Store RFP metadata in the chunk's metadata field, not in content.
    Only add minimal section context to help with retrieval.

    Args:
        chunk: ContextualChunk from ShipleyRFPChunker

    Returns:
        Clean content string with minimal section context
    """
    # SIMPLIFIED: Only add minimal section context
    # LightRAG's entity extraction works best with clean text
    
    context_prefix = f"[RFP Section {chunk.section_id}: {chunk.section_title}]\n\n"
    
    # Safety: Truncate extremely long chunks to prevent timeout
    # This shouldn't happen with proper chunk_size settings, but provides safety
    MAX_CHUNK_LENGTH = 8000  # characters, not tokens
    content = chunk.content
    if len(content) > MAX_CHUNK_LENGTH:
        logger.warning(f"⚠️ Chunk {chunk.chunk_id} exceeds {MAX_CHUNK_LENGTH} chars, truncating")
        content = content[:MAX_CHUNK_LENGTH] + "\n\n[Content truncated for processing]"
    
    # Return clean content with minimal context
    return context_prefix + content


def get_chunk_metadata(chunk_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve metadata for a specific chunk by its ID.
    
    This is useful for logging section information when LightRAG processes chunks,
    or for post-processing analysis of which sections had processing issues.
    
    Args:
        chunk_id: The chunk ID (hash) to look up
        
    Returns:
        Metadata dict with section info, or None if not found
    """
    return _CHUNK_METADATA_MAP.get(chunk_id)


def clear_chunk_metadata():
    """
    Clear the global chunk metadata mapping.
    
    Call this between document processing runs to avoid memory buildup.
    """
    global _CHUNK_METADATA_MAP
    _CHUNK_METADATA_MAP = {}
    logger.info("🧹 Cleared chunk metadata mapping")


def get_all_chunk_metadata() -> Dict[str, Dict[str, Any]]:
    """
    Get all chunk metadata for the current document.
    
    Useful for post-processing analysis or debugging.
    
    Returns:
        Dictionary mapping chunk_id -> metadata
    """
    return _CHUNK_METADATA_MAP.copy()


# Convenience function for testing
def test_chunking_function():
    """Test the chunking function with sample content"""
    sample_rfp = """
    SECTION C - STATEMENT OF WORK

    The contractor shall provide the following services:

    C.1.1 General Requirements
    The contractor must have experience with federal contracting.

    SECTION L - INSTRUCTIONS TO OFFERORS

    L.3.1 Proposal Format
    Proposals shall be submitted in PDF format.
    """

    chunks = rfp_aware_chunking_func(sample_rfp)
    print(f"Generated {len(chunks)} chunks")

    for i, chunk in enumerate(chunks):
        print(f"\nChunk {i+1}:")
        print(f"Content length: {len(chunk['content'])}")
        print(f"Metadata: {chunk['metadata']}")


if __name__ == "__main__":
    test_chunking_function()