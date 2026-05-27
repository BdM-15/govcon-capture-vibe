"""Batch processing callback for document ingestion workflows."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from datetime import datetime

from lightrag.api.config import global_args

from src.core import get_settings

logger = logging.getLogger(__name__)


class GovConProcessingCallback:
    """Track document lifecycle and trigger semantic post-processing per batch."""

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
        self._llm_func = None

    def set_llm_func(self, llm_func):
        """Set the LLM function for post-processing during server init."""
        self._llm_func = llm_func

    async def register_request_start(self, filename: str):
        """Register that an upload request has started at the HTTP layer."""
        with self.lock:
            self.pending_uploads.add(filename)
            self.enhancement_pending = True
            self._cancel_batch_timer()
            logger.info("📥 Upload request started: %s (pending: %d)", filename, len(self.pending_uploads))

    async def register_request_end(self, filename: str):
        """Register that an upload request has finished at the HTTP layer."""
        with self.lock:
            self.pending_uploads.discard(filename)
            logger.info("🏁 Upload request finished: %s (pending: %d)", filename, len(self.pending_uploads))

    def on_document_complete(self, file_path: str, doc_id: str = "", duration_seconds: float = 0.0, **kwargs):
        """Called when a document finishes processing."""
        with self.lock:
            self.processing_docs.discard(doc_id)
            self.completed_docs.add(doc_id)
            self.last_completion_time = datetime.now()
            logger.info(
                "✅ Document completed: %s (%.1fs, queue: %d remaining)",
                doc_id,
                duration_seconds,
                len(self.processing_docs),
            )
            self._schedule_batch_check()

    def on_parse_complete(self, file_path: str, content_blocks: int = 0, doc_id: str = "", duration_seconds: float = 0.0, **kwargs):
        """Called when MinerU parsing completes."""
        with self.lock:
            self.processing_docs.add(doc_id)
            logger.info("⚙️ Parse complete: %s (%d blocks, %.1fs)", doc_id, content_blocks, duration_seconds)

    def on_document_error(self, file_path: str, error: str = "", doc_id: str = "", **kwargs):
        """Called when document processing fails."""
        with self.lock:
            self.processing_docs.discard(doc_id)
            self.completed_docs.add(doc_id)
            self.last_completion_time = datetime.now()
            logger.error("❌ Document error: %s - %s", doc_id, error)
            self._schedule_batch_check()

    def _cancel_batch_timer(self):
        """Cancel any pending batch completion timer."""
        if self._batch_timer is not None:
            self._batch_timer.cancel()
            self._batch_timer = None

    def _schedule_batch_check(self):
        """Schedule a batch completion check after timeout."""
        self._cancel_batch_timer()
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(
            self.batch_timeout_seconds,
            lambda: asyncio.ensure_future(self._check_batch_complete()),
        )

    async def _check_batch_complete(self):
        """Check whether the current batch is complete and trigger enhancement."""
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
            logger.info("🎯 BATCH COMPLETE - %d documents, %ss idle", doc_count, self.batch_timeout_seconds)
            logger.info(
                "⏭️ Post-processing DISABLED (ENABLE_POST_PROCESSING=false). Skipping semantic enhancement."
            )
            with self.lock:
                self.completed_docs.clear()
                self.enhancement_pending = False
                self.enhancement_running = False
            return

        logger.info("🎯 BATCH COMPLETE - %d documents, %ss idle", doc_count, self.batch_timeout_seconds)

        try:
            from src.inference.semantic_post_processor import enhance_knowledge_graph

            workspace_rag_path = os.path.join(global_args.working_dir, get_settings().workspace)
            inference_result = await enhance_knowledge_graph(
                rag_storage_path=workspace_rag_path,
                llm_func=self._llm_func,
                batch_size=50,
            )

            logger.info("✅ Cumulative semantic enhancement complete")
            logger.info("   Final Neo4j entities: %d", inference_result.get("final_entity_count", 0))
            logger.info(
                "   Final Neo4j relationships: %d",
                inference_result.get("final_relationship_count", 0),
            )
            logger.info(
                "   Final VDB relationship entries: %d",
                inference_result.get("vdb_relationship_count", 0),
            )
            logger.info("   Entities corrected: %d", inference_result.get("entities_corrected", 0))
            logger.info(
                "   Relationships inferred: %d",
                inference_result.get("relationships_inferred", 0),
            )
            logger.info("   View results in Neo4j Browser: http://localhost:7474")
        except Exception as exc:
            logger.error("❌ Batch enhancement failed: %s", exc)
            import traceback

            logger.error(traceback.format_exc())
        finally:
            with self.lock:
                self.completed_docs.clear()
                self.enhancement_pending = False
                self.enhancement_running = False
                logger.info("🔄 Batch state reset - ready for next upload batch")

    async def get_stats(self) -> dict:
        """Return current queue statistics."""
        with self.lock:
            return {
                "pending_uploads": len(self.pending_uploads),
                "processing": len(self.processing_docs),
                "completed": len(self.completed_docs),
                "enhancement_pending": self.enhancement_pending,
                "enhancement_running": self.enhancement_running,
            }


_callback = GovConProcessingCallback()


def get_processing_callback() -> GovConProcessingCallback:
    """Get the global processing callback for registration in initialization.py."""
    return _callback