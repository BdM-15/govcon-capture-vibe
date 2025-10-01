"""
LightRAG Integration for RFP-Aware Chunking

Integrates ShipleyRFPChunker with LightRAG's document processing pipeline
to maintain RFP section structure and relationships in the knowledge graph.

This module provides seamless integration with LightRAG's WebUI by automatically
detecting and processing RFP documents with enhanced section-aware chunking.
"""

import asyncio
import logging
import re
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

from lightrag import LightRAG
from lightrag.base import BaseKVStorage
from lightrag.utils import logger as lightrag_logger

# Import RFP chunking components
from src.core.chunking import ShipleyRFPChunker, ContextualChunk

logger = logging.getLogger(__name__)

class RFPAwareLightRAG:
    """
    Enhanced LightRAG processor with automatic RFP detection and enhanced chunking
    
    This class wraps LightRAG functionality while automatically detecting RFP documents
    and applying enhanced section-aware processing. It maintains full compatibility
    with the LightRAG WebUI while providing superior RFP analysis capabilities.
    """
    
    def __init__(self, lightrag_instance: LightRAG):
        """Initialize with existing LightRAG instance"""
        self.lightrag = lightrag_instance
        self.chunker = ShipleyRFPChunker()
        self.rfp_chunks: List[ContextualChunk] = []
        self.section_summary: Dict[str, Any] = {}
        self.processed_documents: Dict[str, Dict[str, Any]] = {}
        
        # RFP detection patterns
        self.rfp_patterns = [
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
        
        lightrag_logger.info("🎯 RFP-Aware LightRAG initialized - enhanced processing ready")
    
    def detect_rfp_document(self, document_text: str, file_path: Optional[str] = None) -> bool:
        """
        Detect if a document is likely an RFP based on content and filename patterns
        
        Args:
            document_text: Document content to analyze
            file_path: Optional path to the document file
            
        Returns:
            bool: True if document appears to be an RFP
        """
        pattern_matches = 0
        content_lower = document_text.lower()
        
        # Check filename for RFP indicators
        if file_path:
            filename = Path(file_path).name.lower()
            rfp_filename_patterns = [
                r'rfp', r'solicitation', r'proposal', r'sow', r'pws',
                r'n\d+', r'w\d+', r'gs\d+', r'sp\d+'  # Common govt solicitation numbers
            ]
            
            for pattern in rfp_filename_patterns:
                if re.search(pattern, filename):
                    lightrag_logger.info(f"📄 RFP detected by filename pattern: {pattern}")
                    return True
        
        # Check content for RFP patterns
        for pattern in self.rfp_patterns:
            if re.search(pattern, content_lower):
                pattern_matches += 1
                lightrag_logger.debug(f"🔍 RFP pattern match: {pattern}")
        
        # Check for section structure (strong indicator)
        section_pattern = r'section\s+[a-m]\s*[\.\:]'
        if re.search(section_pattern, content_lower):
            pattern_matches += 2  # Weight section patterns more heavily
        
        # Check for multiple sections
        sections_found = len(re.findall(r'section\s+[a-m]', content_lower))
        if sections_found >= 3:
            pattern_matches += 3  # Strong indicator of RFP structure
        
        # Require multiple pattern matches for content-based detection
        is_rfp = pattern_matches >= 3
        
        if is_rfp:
            lightrag_logger.info(f"📋 RFP document detected with {pattern_matches} pattern matches, {sections_found} sections")
        else:
            lightrag_logger.info(f"📄 Document does not appear to be an RFP ({pattern_matches} pattern matches)")
        
        return is_rfp
    
    async def ainsert(self, content: Union[str, List[str]], **kwargs) -> Any:
        """
        Enhanced insert method that automatically applies RFP processing when detected
        
        This method maintains compatibility with LightRAG's ainsert while adding
        automatic RFP detection and enhanced processing.
        
        Args:
            content: Document content (string or list of strings)
            **kwargs: Additional parameters for LightRAG processing
            
        Returns:
            LightRAG processing results with enhanced metadata
        """
        # Handle list input
        if isinstance(content, list):
            results = []
            for doc in content:
                result = await self.ainsert(doc, **kwargs)
                results.append(result)
            return results
        
        # Process single document
        document_text = str(content)
        file_path = kwargs.get('file_path', 'unknown_document')
        
        try:
            # Detect if this is an RFP document
            is_rfp = self.detect_rfp_document(document_text, file_path)
            
            if is_rfp:
                lightrag_logger.info("🎯 Processing document with enhanced RFP analysis")
                return await self._process_as_rfp(document_text, file_path, **kwargs)
            else:
                lightrag_logger.info("📄 Processing document with standard LightRAG")
                return await self.lightrag.ainsert(document_text, **kwargs)
                
        except Exception as e:
            lightrag_logger.error(f"❌ Error in enhanced processing, falling back to standard: {e}")
            # Fallback to standard LightRAG processing
            return await self.lightrag.ainsert(document_text, **kwargs)
    
    async def _process_as_rfp(self, document_text: str, file_path: str, **kwargs) -> Dict[str, Any]:
        """Internal method to process document as RFP using enhanced chunking"""
        try:
            # Process with enhanced RFP chunking
            processing_result = await self.process_rfp_document(document_text, file_path)
            
            # Store metadata about this processing
            self.processed_documents[file_path] = {
                "processing_type": "enhanced_rfp",
                "timestamp": asyncio.get_event_loop().time(),
                "status": processing_result.get("status", "unknown"),
                "sections_found": processing_result.get("sections_identified", []),
                "chunks_created": processing_result.get("chunks_processed", 0)
            }
            
            lightrag_logger.info(f"✅ Enhanced RFP processing complete for {file_path}")
            
            # Return result in LightRAG-compatible format
            return {
                "status": "success",
                "enhanced_processing": True,
                "rfp_analysis": processing_result,
                "file_path": file_path
            }
            
        except Exception as e:
            lightrag_logger.error(f"❌ Enhanced RFP processing failed for {file_path}: {e}")
            # Record the failure and fallback
            self.processed_documents[file_path] = {
                "processing_type": "fallback_standard",
                "timestamp": asyncio.get_event_loop().time(),
                "status": "enhanced_failed",
                "error": str(e)
            }
            
            # Fallback to standard processing
            return await self.lightrag.ainsert(document_text, **kwargs)
    
    async def aquery(self, query: str, **kwargs) -> Any:
        """
        Enhanced query method with RFP awareness
        
        Automatically enhances queries for RFP content when RFP documents
        have been processed, while maintaining full LightRAG compatibility.
        
        Args:
            query: Search query
            **kwargs: Additional parameters for LightRAG query
            
        Returns:
            Enhanced query results with RFP context when applicable
        """
        try:
            # Check if we have processed RFP documents
            has_rfp_content = any(
                doc_info.get("processing_type") == "enhanced_rfp" 
                for doc_info in self.processed_documents.values()
            )
            
            if has_rfp_content:
                # Detect if query is RFP-related
                rfp_query_patterns = [
                    r'section\s+[a-m]', r'requirement', r'compliance', r'evaluation',
                    r'proposal', r'offeror', r'solicitation', r'attachment',
                    r'instructions', r'factors', r'award', r'clause'
                ]
                
                is_rfp_query = any(re.search(pattern, query.lower()) for pattern in rfp_query_patterns)
                
                if is_rfp_query:
                    # Enhance query with RFP context
                    enhanced_query = f"""
{query}

[ANALYSIS CONTEXT: This query relates to RFP analysis. Focus on section-specific content, requirements, compliance factors, and relationships between sections. Pay special attention to L-M section relationships (Instructions to Offerors ↔ Evaluation Factors).]
"""
                    lightrag_logger.info("🎯 Enhanced RFP-aware query with section context")
                    return await self.lightrag.aquery(enhanced_query, **kwargs)
            
            # Standard query processing
            return await self.lightrag.aquery(query, **kwargs)
            
        except Exception as e:
            lightrag_logger.error(f"❌ Error in enhanced query: {e}")
            # Fallback to standard query
            return await self.lightrag.aquery(query, **kwargs)
        
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
    
    def get_processing_status(self) -> Dict[str, Any]:
        """Get status of all processed documents"""
        rfp_count = sum(1 for doc in self.processed_documents.values() 
                       if doc.get("processing_type") == "enhanced_rfp")
        
        return {
            "total_documents": len(self.processed_documents),
            "rfp_documents": rfp_count,
            "standard_documents": len(self.processed_documents) - rfp_count,
            "enhanced_processing_available": True,
            "processed_documents": self.processed_documents.copy()
        }
    
    def is_rfp_processed(self, file_path: str) -> bool:
        """Check if a specific file was processed as an RFP"""
        doc_info = self.processed_documents.get(file_path, {})
        return doc_info.get("processing_type") == "enhanced_rfp"
    
    # Delegate all other LightRAG methods
    def __getattr__(self, name):
        """Delegate unknown methods to the underlying LightRAG instance"""
        return getattr(self.lightrag, name)

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