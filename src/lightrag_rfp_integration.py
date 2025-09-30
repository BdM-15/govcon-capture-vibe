"""
LightRAG Integration for RFP-Aware Chunking

Integrates ShipleyRFPChunker with LightRAG's document processing pipeline
to maintain RFP section structure and relationships in the knowledge graph.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from lightrag import LightRAG
from lightrag.base import BaseKVStorage
from lightrag.utils import logger as lightrag_logger

# Import RFP chunking components
import sys
sys.path.append(str(Path(__file__).parent))
from rfp_chunking import ShipleyRFPChunker, ContextualChunk

logger = logging.getLogger(__name__)

class RFPAwareLightRAG:
    """
    Enhanced LightRAG processor with RFP-aware chunking capabilities
    
    Wraps standard LightRAG functionality while using custom RFP chunking
    that preserves section structure and relationships.
    """
    
    def __init__(self, lightrag_instance: LightRAG):
        """Initialize with existing LightRAG instance"""
        self.lightrag = lightrag_instance
        self.chunker = ShipleyRFPChunker()
        self.rfp_chunks: List[ContextualChunk] = []
        self.section_summary: Dict[str, Any] = {}
        
    async def process_rfp_document(self, document_text: str, file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Process RFP document using section-aware chunking
        
        Args:
            document_text: Full RFP document text
            file_path: Optional path to source file
            
        Returns:
            Dictionary with processing results and section analysis
        """
        logger.info("Starting RFP-aware document processing")
        
        try:
            # Step 1: Use custom RFP chunking
            self.rfp_chunks = self.chunker.process_document(document_text)
            
            # Step 2: Generate section summary
            self.section_summary = self.chunker.get_section_summary(self.rfp_chunks)
            
            # Step 3: Convert to LightRAG format and process
            lightrag_results = await self._process_chunks_with_lightrag(file_path or "rfp_document.pdf")
            
            # Step 4: Enhance knowledge graph with section metadata
            await self._enhance_knowledge_graph_with_sections()
            
            processing_results = {
                "status": "success",
                "file_path": file_path,
                "section_summary": self.section_summary,
                "chunks_processed": len(self.rfp_chunks),
                "lightrag_results": lightrag_results,
                "sections_identified": self.section_summary.get("sections_identified", []),
                "total_sections": self.section_summary.get("total_sections", 0),
                "sections_with_requirements": self.section_summary.get("sections_with_requirements", [])
            }
            
            logger.info(f"RFP processing complete: {len(self.rfp_chunks)} chunks, {processing_results['total_sections']} sections")
            return processing_results
            
        except Exception as e:
            logger.error(f"RFP document processing failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "file_path": file_path
            }
    
    async def _process_chunks_with_lightrag(self, file_path: str) -> Dict[str, Any]:
        """Process RFP chunks through LightRAG pipeline"""
        
        # Prepare chunks in LightRAG format
        chunk_texts = []
        chunk_metadata = []
        
        for chunk in self.rfp_chunks:
            # Enhanced chunk text with section context
            enhanced_text = self._create_enhanced_chunk_text(chunk)
            chunk_texts.append(enhanced_text)
            
            # Metadata for tracking
            metadata = {
                "chunk_id": chunk.chunk_id,
                "section_id": chunk.section_id,
                "section_title": chunk.section_title,
                "subsection_id": chunk.subsection_id,
                "chunk_order": chunk.chunk_order,
                "page_number": chunk.page_number,
                "relationships": chunk.relationships,
                "requirements_count": len(chunk.requirements),
                "has_requirements": len(chunk.requirements) > 0,
                **chunk.metadata
            }
            chunk_metadata.append(metadata)
        
        # Process through LightRAG in batches to avoid memory issues
        batch_size = 10  # Process in smaller batches
        results = []
        
        for i in range(0, len(chunk_texts), batch_size):
            batch_texts = chunk_texts[i:i + batch_size]
            batch_metadata = chunk_metadata[i:i + batch_size]
            
            logger.info(f"Processing chunk batch {i//batch_size + 1}/{(len(chunk_texts)-1)//batch_size + 1}")
            
            # Join batch texts for LightRAG processing
            batch_combined = "\n\n--- CHUNK SEPARATOR ---\n\n".join(batch_texts)
            
            try:
                # Use LightRAG's ainsert method
                batch_result = await self.lightrag.ainsert(batch_combined)
                results.append({
                    "batch": i//batch_size + 1,
                    "chunks_processed": len(batch_texts),
                    "result": batch_result,
                    "metadata": batch_metadata
                })
                
            except Exception as e:
                logger.error(f"Batch processing failed for batch {i//batch_size + 1}: {e}")
                results.append({
                    "batch": i//batch_size + 1,
                    "chunks_processed": len(batch_texts),
                    "error": str(e),
                    "metadata": batch_metadata
                })
        
        return {
            "batches_processed": len(results),
            "total_chunks": len(chunk_texts),
            "batch_results": results
        }
    
    def _create_enhanced_chunk_text(self, chunk: ContextualChunk) -> str:
        """Create enhanced chunk text with section context for LightRAG"""
        
        # Build context header
        context_lines = [
            f"=== RFP SECTION: {chunk.section_id} - {chunk.section_title} ==="
        ]
        
        if chunk.subsection_id:
            context_lines.append(f"Subsection: {chunk.subsection_id}")
        
        if chunk.page_number:
            context_lines.append(f"Page: {chunk.page_number}")
        
        if chunk.relationships:
            context_lines.append(f"Related Sections: {', '.join(chunk.relationships)}")
        
        if chunk.requirements:
            context_lines.append(f"Requirements Identified: {len(chunk.requirements)}")
        
        # Add metadata context
        if chunk.metadata:
            if chunk.metadata.get("has_requirements"):
                context_lines.append("Contains requirement statements")
            if chunk.metadata.get("section_type"):
                context_lines.append(f"Section Type: {chunk.metadata['section_type']}")
        
        context_lines.append("--- CONTENT ---")
        
        # Build enhanced text
        enhanced_text = "\n".join(context_lines) + "\n\n" + chunk.content
        
        # Add requirements section if present
        if chunk.requirements:
            enhanced_text += "\n\n--- IDENTIFIED REQUIREMENTS ---\n"
            for i, req in enumerate(chunk.requirements, 1):
                enhanced_text += f"{i}. {req}\n"
        
        return enhanced_text
    
    async def _enhance_knowledge_graph_with_sections(self):
        """Add section-specific metadata to the knowledge graph"""
        
        try:
            # Store section summary in LightRAG's key-value storage
            if hasattr(self.lightrag, 'key_string_value_json_storage_cls'):
                kv_storage = self.lightrag.key_string_value_json_storage_cls(
                    namespace="rfp_sections",
                    global_config=self.lightrag.global_config
                )
                
                # Store section summary
                await kv_storage.aset("section_summary", self.section_summary)
                
                # Store individual section details
                for section_id, section_data in self.section_summary.get("section_details", {}).items():
                    await kv_storage.aset(f"section_{section_id}", section_data)
                
                # Store chunk mapping
                chunk_mapping = {}
                for chunk in self.rfp_chunks:
                    chunk_mapping[chunk.chunk_id] = {
                        "section_id": chunk.section_id,
                        "section_title": chunk.section_title,
                        "subsection_id": chunk.subsection_id,
                        "relationships": chunk.relationships,
                        "requirements_count": len(chunk.requirements)
                    }
                
                await kv_storage.aset("chunk_section_mapping", chunk_mapping)
                
                logger.info("Enhanced knowledge graph with RFP section metadata")
                
        except Exception as e:
            logger.warning(f"Could not enhance knowledge graph with section metadata: {e}")
    
    async def query_by_section(self, section_id: str, query: str = "") -> Dict[str, Any]:
        """
        Query specific RFP section content
        
        Args:
            section_id: RFP section identifier (A, B, C, L, M, etc.)
            query: Optional specific query within the section
            
        Returns:
            Section-specific query results
        """
        
        # Find chunks for this section
        section_chunks = [chunk for chunk in self.rfp_chunks if chunk.section_id.startswith(section_id)]
        
        if not section_chunks:
            return {
                "status": "not_found",
                "section_id": section_id,
                "message": f"Section {section_id} not found in processed RFP"
            }
        
        # Build section-specific query
        if query:
            section_query = f"In RFP Section {section_id}, {query}"
        else:
            section_query = f"Summarize RFP Section {section_id} content and requirements"
        
        try:
            # Use LightRAG query with section context
            from lightrag import QueryParam
            
            query_param = QueryParam(
                mode="hybrid",
                user_prompt=f"Focus on RFP Section {section_id} content. Use only information from this specific section.",
                stream=False
            )
            
            result = await self.lightrag.aquery_llm(section_query, param=query_param)
            
            return {
                "status": "success",
                "section_id": section_id,
                "query": query,
                "chunks_found": len(section_chunks),
                "section_title": section_chunks[0].section_title if section_chunks else "",
                "result": result,
                "section_metadata": {
                    "subsections": list(set(chunk.subsection_id for chunk in section_chunks if chunk.subsection_id)),
                    "total_requirements": sum(len(chunk.requirements) for chunk in section_chunks),
                    "related_sections": list(set().union(*[chunk.relationships for chunk in section_chunks]))
                }
            }
            
        except Exception as e:
            logger.error(f"Section query failed for {section_id}: {e}")
            return {
                "status": "error",
                "section_id": section_id,
                "error": str(e)
            }
    
    async def get_section_relationships(self, section_id: str) -> Dict[str, Any]:
        """Get relationships for a specific section"""
        
        section_chunks = [chunk for chunk in self.rfp_chunks if chunk.section_id.startswith(section_id)]
        
        if not section_chunks:
            return {"error": f"Section {section_id} not found"}
        
        # Aggregate relationships
        all_relationships = set()
        requirements_count = 0
        subsections = set()
        
        for chunk in section_chunks:
            all_relationships.update(chunk.relationships)
            requirements_count += len(chunk.requirements)
            if chunk.subsection_id:
                subsections.add(chunk.subsection_id)
        
        return {
            "section_id": section_id,
            "section_title": section_chunks[0].section_title,
            "related_sections": list(all_relationships),
            "subsections": list(subsections),
            "total_requirements": requirements_count,
            "chunk_count": len(section_chunks)
        }
    
    def get_processing_summary(self) -> Dict[str, Any]:
        """Get summary of RFP processing results"""
        return {
            "chunks_created": len(self.rfp_chunks),
            "section_summary": self.section_summary,
            "sections_with_requirements": [
                section_id for section_id in self.section_summary.get("sections_identified", [])
                if any(chunk.requirements for chunk in self.rfp_chunks if chunk.section_id == section_id)
            ],
            "total_requirements": sum(len(chunk.requirements) for chunk in self.rfp_chunks),
            "processing_metadata": {
                "chunker_used": "ShipleyRFPChunker",
                "lightrag_integration": "enabled",
                "section_awareness": "enabled",
                "relationship_mapping": "enabled"
            }
        }

# Convenience function for easy integration
async def process_rfp_with_lightrag(lightrag_instance: LightRAG, document_text: str, file_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to process RFP with enhanced chunking
    
    Args:
        lightrag_instance: Configured LightRAG instance
        document_text: RFP document text
        file_path: Optional source file path
        
    Returns:
        Processing results with section analysis
    """
    processor = RFPAwareLightRAG(lightrag_instance)
    return await processor.process_rfp_document(document_text, file_path)