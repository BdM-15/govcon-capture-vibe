"""
Chunk Progress Logger with Section Visibility

Provides real-time visibility into which RFP sections are being processed during
LightRAG document processing. Logs section metadata (section_id, section_title,
subsection_id, page_number, requirements_count) for performance tracking and
optimization.

Usage:
    from src.utils.chunk_progress_logger import ChunkProgressLogger
    
    logger = ChunkProgressLogger()
    logger.log_chunk_start(chunk_index, total_chunks, chunk_metadata)
    # ... processing ...
    logger.log_chunk_complete(chunk_index, processing_time_seconds, entity_count, relation_count)
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ChunkProgressLogger:
    """Logs chunk processing progress with RFP section metadata visibility."""
    
    def __init__(self):
        """Initialize the chunk progress logger."""
        self.processing_stats = {}
        self.start_times = {}
        
    def log_chunk_start(
        self,
        chunk_index: int,
        total_chunks: int,
        chunk_metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log the start of chunk processing with section metadata.
        
        Args:
            chunk_index: Current chunk number (1-indexed)
            total_chunks: Total number of chunks to process
            chunk_metadata: Optional metadata dict containing:
                - section_id: RFP section identifier (e.g., "C", "L", "J-1")
                - section_title: Section name (e.g., "Statement of Work")
                - subsection_id: Detailed subsection (e.g., "C.3.1")
                - chunk_order: Sequential chunk order within document
                - page_number: Page location in original document
                - requirements_count: Number of requirements in chunk
                - rfp_enhanced: Whether RFP-aware chunking was applied
        """
        self.start_times[chunk_index] = datetime.now()
        
        # Build section info string
        section_info = ""
        if chunk_metadata:
            section_id = chunk_metadata.get('section_id', 'Unknown')
            section_title = chunk_metadata.get('section_title', 'Unknown Section')
            subsection_id = chunk_metadata.get('subsection_id', '')
            page_number = chunk_metadata.get('page_number', '?')
            requirements_count = chunk_metadata.get('requirements_count', 0)
            
            # Format: "Section C - Statement of Work (C.3.1, Page 45, 8 reqs)"
            section_info = f"Section {section_id} - {section_title}"
            if subsection_id:
                section_info += f" ({subsection_id}"
            else:
                section_info += f" (Page {page_number}"
                
            if requirements_count > 0:
                section_info += f", {requirements_count} reqs)"
            else:
                section_info += ")"
        else:
            section_info = "Section metadata not available"
        
        logger.info(
            f"⚙️  Processing Chunk {chunk_index}/{total_chunks}: {section_info}"
        )
        
    def log_chunk_complete(
        self,
        chunk_index: int,
        entity_count: int = 0,
        relation_count: int = 0,
        chunk_metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log the completion of chunk processing with timing and extraction stats.
        
        Args:
            chunk_index: Current chunk number (1-indexed)
            entity_count: Number of entities extracted
            relation_count: Number of relationships extracted
            chunk_metadata: Optional metadata for additional context
        """
        if chunk_index in self.start_times:
            elapsed = (datetime.now() - self.start_times[chunk_index]).total_seconds()
            
            # Store stats for later analysis
            section_id = "Unknown"
            if chunk_metadata:
                section_id = chunk_metadata.get('section_id', 'Unknown')
                
            self.processing_stats[chunk_index] = {
                'section_id': section_id,
                'processing_time': elapsed,
                'entity_count': entity_count,
                'relation_count': relation_count,
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(
                f"✅ Chunk {chunk_index} completed in {elapsed:.1f}s "
                f"({entity_count} Ent + {relation_count} Rel)"
            )
        else:
            logger.warning(f"Chunk {chunk_index} completion logged without start time")
    
    def log_chunk_timeout(
        self,
        chunk_index: int,
        total_chunks: int,
        chunk_metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a chunk processing timeout with section information.
        
        Args:
            chunk_index: Current chunk number (1-indexed)
            total_chunks: Total number of chunks
            chunk_metadata: Optional metadata for troubleshooting
        """
        section_info = "Unknown Section"
        if chunk_metadata:
            section_id = chunk_metadata.get('section_id', 'Unknown')
            section_title = chunk_metadata.get('section_title', 'Unknown Section')
            subsection_id = chunk_metadata.get('subsection_id', '')
            page_number = chunk_metadata.get('page_number', '?')
            
            section_info = f"Section {section_id} - {section_title}"
            if subsection_id:
                section_info += f" ({subsection_id}, Page {page_number})"
            else:
                section_info += f" (Page {page_number})"
        
        elapsed = 0
        if chunk_index in self.start_times:
            elapsed = (datetime.now() - self.start_times[chunk_index]).total_seconds()
        
        logger.error(
            f"⏱️  TIMEOUT: Chunk {chunk_index}/{total_chunks} - {section_info} "
            f"(exceeded timeout after {elapsed:.1f}s)"
        )
        
    def get_section_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics grouped by section.
        
        Returns:
            Dictionary mapping section_id to aggregated stats:
                - chunk_count: Number of chunks in section
                - avg_time: Average processing time
                - max_time: Maximum processing time
                - total_entities: Total entities extracted
                - total_relations: Total relationships extracted
        """
        section_stats = {}
        
        for chunk_idx, stats in self.processing_stats.items():
            section_id = stats['section_id']
            
            if section_id not in section_stats:
                section_stats[section_id] = {
                    'chunk_count': 0,
                    'total_time': 0,
                    'max_time': 0,
                    'total_entities': 0,
                    'total_relations': 0,
                    'chunk_times': []
                }
            
            section_stats[section_id]['chunk_count'] += 1
            section_stats[section_id]['total_time'] += stats['processing_time']
            section_stats[section_id]['max_time'] = max(
                section_stats[section_id]['max_time'],
                stats['processing_time']
            )
            section_stats[section_id]['total_entities'] += stats['entity_count']
            section_stats[section_id]['total_relations'] += stats['relation_count']
            section_stats[section_id]['chunk_times'].append(stats['processing_time'])
        
        # Calculate averages
        for section_id, stats in section_stats.items():
            if stats['chunk_count'] > 0:
                stats['avg_time'] = stats['total_time'] / stats['chunk_count']
        
        return section_stats
    
    def log_summary(self) -> None:
        """Log a summary of processing statistics by section."""
        section_stats = self.get_section_stats()
        
        if not section_stats:
            logger.info("No processing statistics available")
            return
        
        logger.info("=" * 80)
        logger.info("📊 SECTION PROCESSING SUMMARY")
        logger.info("=" * 80)
        
        for section_id in sorted(section_stats.keys()):
            stats = section_stats[section_id]
            logger.info(
                f"Section {section_id}: {stats['chunk_count']} chunks, "
                f"avg {stats['avg_time']:.1f}s, max {stats['max_time']:.1f}s, "
                f"{stats['total_entities']} entities, {stats['total_relations']} relations"
            )
        
        logger.info("=" * 80)
