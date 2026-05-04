"""
FastAPI Routes Module

Custom endpoints for RAG-Anything + LightRAG server:
- /insert: Document upload with automatic semantic post-processing
- /documents/upload: WebUI document upload (also triggers post-processing)

Architecture:
1. Document Upload → process_document_with_semantic_inference()
2. RAG-Anything Processing → MinerU multimodal parsing
3. Native LightRAG Extraction → Entity/relationship extraction (18 types)
4. GovConProcessingCallback → Detects batch completion via RAG-Anything callbacks
5. Auto-Enhancement → Semantic post-processing runs ONCE after last document
"""

import os
import asyncio
import logging
import threading
from datetime import datetime
from fastapi import BackgroundTasks
from lightrag.api.config import global_args
from raganything.callbacks import ProcessingCallback

from src.core import get_settings
from src.server.document_processing import process_document_with_semantic_inference as run_document_processing
from src.server.scan_routes import create_scan_endpoint as register_scan_endpoint
from src.server.upload_routes import (
    create_documents_upload_endpoint as register_documents_upload_endpoint,
    create_insert_endpoint as register_insert_endpoint,
)

logger = logging.getLogger(__name__)


# ============================================================================
# BATCH PROCESSING CALLBACK (RAG-Anything ProcessingCallback)
# ============================================================================
# Replaces the polling-based DocumentQueueTracker with event-driven callbacks.
# Batch completion is detected via a timeout timer that resets on each document
# completion event — no asyncio.sleep polling loop.

class GovConProcessingCallback(ProcessingCallback):
    """
    Callback handler for batch document processing with auto-enhancement.
    
    Tracks document lifecycle and triggers semantic post-processing when a 
    batch completes (no new documents within timeout window).
    """
    
    def __init__(self):
        settings = get_settings()
        self.batch_timeout_seconds = settings.batch_timeout_seconds
        self.pending_uploads: set[str] = set()
        self.processing_docs: set[str] = set()
        self.completed_docs: set[str] = set()
        self.last_completion_time: datetime | None = None
        self.enhancement_pending = False
        self.enhancement_running = False
        self.lock = threading.Lock()
        self._batch_timer: asyncio.TimerHandle | None = None
        self._llm_func = None  # Set during initialization
    
    def set_llm_func(self, llm_func):
        """Set the LLM function for post-processing (called during server init)."""
        self._llm_func = llm_func
    
    async def register_request_start(self, filename: str):
        """Register that an upload request has started (HTTP layer)."""
        with self.lock:
            self.pending_uploads.add(filename)
            self.enhancement_pending = True
            self._cancel_batch_timer()
            logger.info(f"📥 Upload request started: {filename} (pending: {len(self.pending_uploads)})")

    async def register_request_end(self, filename: str):
        """Register that an upload request has finished (HTTP layer)."""
        with self.lock:
            self.pending_uploads.discard(filename)
            logger.info(f"🏁 Upload request finished: {filename} (pending: {len(self.pending_uploads)})")

    # --- RAG-Anything ProcessingCallback overrides ---
    
    def on_document_complete(self, file_path: str, doc_id: str = '', 
                              duration_seconds: float = 0.0, **kwargs):
        """Called when a document finishes processing (sync — called by dispatch)."""
        with self.lock:
            self.processing_docs.discard(doc_id)
            self.completed_docs.add(doc_id)
            self.last_completion_time = datetime.now()
            logger.info(f"✅ Document completed: {doc_id} ({duration_seconds:.1f}s, "
                        f"queue: {len(self.processing_docs)} remaining)")
            self._schedule_batch_check()

    def on_parse_complete(self, file_path: str, content_blocks: int = 0,
                           doc_id: str = '', duration_seconds: float = 0.0, **kwargs):
        """Called when MinerU parsing completes (sync — called by dispatch)."""
        with self.lock:
            self.processing_docs.add(doc_id)
            logger.info(f"⚙️ Parse complete: {doc_id} ({content_blocks} blocks, {duration_seconds:.1f}s)")

    def on_document_error(self, file_path: str, error: str = '',
                           doc_id: str = '', **kwargs):
        """Called when document processing fails (sync — called by dispatch)."""
        with self.lock:
            self.processing_docs.discard(doc_id)
            self.completed_docs.add(doc_id)  # Count as completed to not block batch
            self.last_completion_time = datetime.now()
            logger.error(f"❌ Document error: {doc_id} - {error}")
            self._schedule_batch_check()

    # --- Batch completion detection ---

    def _cancel_batch_timer(self):
        """Cancel any pending batch completion timer."""
        if self._batch_timer is not None:
            self._batch_timer.cancel()
            self._batch_timer = None

    def _schedule_batch_check(self):
        """Schedule a batch completion check after timeout. Resets on each call."""
        self._cancel_batch_timer()
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(
            self.batch_timeout_seconds,
            lambda: asyncio.ensure_future(self._check_batch_complete())
        )

    async def _check_batch_complete(self):
        """Check if batch is complete and trigger enhancement."""
        settings = get_settings()
        with self.lock:
            if (
                len(self.pending_uploads) == 0
                and len(self.processing_docs) == 0
                and len(self.completed_docs) > 0
                and self.enhancement_pending
                and not self.enhancement_running
            ):
                self.enhancement_running = True
            else:
                return

        doc_count = len(self.completed_docs)

        if not settings.enable_post_processing:
            logger.info(f"🎯 BATCH COMPLETE - {doc_count} documents, "
                         f"{self.batch_timeout_seconds}s idle")
            logger.info("⏭️ Post-processing DISABLED (ENABLE_POST_PROCESSING=false). "
                         "Skipping semantic enhancement.")
            with self.lock:
                self.completed_docs.clear()
                self.enhancement_pending = False
                self.enhancement_running = False
            return

        # Run enhancement outside the lock (async from here)
        logger.info(f"🎯 BATCH COMPLETE - {doc_count} documents, "
                     f"{self.batch_timeout_seconds}s idle")
        
        try:
            from src.inference.semantic_post_processor import enhance_knowledge_graph
            workspace_rag_path = os.path.join(global_args.working_dir, get_settings().workspace)
            
            inference_result = await enhance_knowledge_graph(
                rag_storage_path=workspace_rag_path,
                llm_func=self._llm_func,
                batch_size=50
            )
            
            logger.info("✅ Cumulative semantic enhancement complete")
            logger.info(f"   Final Neo4j entities: {inference_result.get('final_entity_count', 0)}")
            logger.info(f"   Final Neo4j relationships: {inference_result.get('final_relationship_count', 0)}")
            logger.info(f"   Final VDB relationship entries: {inference_result.get('vdb_relationship_count', 0)}")
            logger.info(f"   Entities corrected: {inference_result.get('entities_corrected', 0)}")
            logger.info(f"   Relationships inferred: {inference_result.get('relationships_inferred', 0)}")
            logger.info(f"   View results in Neo4j Browser: http://localhost:7474")
            
        except Exception as e:
            logger.error(f"❌ Batch enhancement failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        finally:
            with self.lock:
                self.completed_docs.clear()
                self.enhancement_pending = False
                self.enhancement_running = False
                logger.info("🔄 Batch state reset - ready for next upload batch")

    async def get_stats(self) -> dict:
        """Get current queue statistics."""
        with self.lock:
            return {
                "pending_uploads": len(self.pending_uploads),
                "processing": len(self.processing_docs),
                "completed": len(self.completed_docs),
                "enhancement_pending": self.enhancement_pending,
                "enhancement_running": self.enhancement_running,
            }

# Global callback instance
_callback = GovConProcessingCallback()


def get_processing_callback() -> GovConProcessingCallback:
    """Get the global processing callback (for registration in initialization.py)."""
    return _callback


async def process_document_with_semantic_inference(
    file_path: str,
    file_name: str,
    rag_instance,
    llm_func
) -> dict:
    return await run_document_processing(
        file_path,
        file_name,
        rag_instance,
        llm_func,
        callback=_callback,
    )


def create_insert_endpoint(app, rag_instance):
    register_insert_endpoint(
        app,
        rag_instance,
        process_document_func=process_document_with_semantic_inference,
        callback=_callback,
    )


def create_documents_upload_endpoint(app, rag_instance):
    register_documents_upload_endpoint(
        app,
        rag_instance,
        process_document_func=process_document_with_semantic_inference,
        callback=_callback,
    )


def create_scan_endpoint(app, rag_instance):
    register_scan_endpoint(
        app,
        rag_instance,
        process_document_func=process_document_with_semantic_inference,
        callback=_callback,
    )


