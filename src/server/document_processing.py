"""Document status helpers for native ingestion."""

from __future__ import annotations

import logging
from typing import Optional

from lightrag.base import DocStatus
from lightrag.utils import compute_mdhash_id

from src.utils.time_utils import now_local_iso

logger = logging.getLogger(__name__)


async def record_failed_doc(
    rag_instance,
    file_path: str,
    file_name: str,
    doc_id: Optional[str],
    error_msg: str,
) -> None:
    """Write failed doc_status entry so UI can surface failures."""
    try:
        if not doc_id:
            doc_id = compute_mdhash_id(file_path, prefix="failed-")
        now = now_local_iso()
        truncated_err = error_msg[:500]
        await rag_instance.lightrag.doc_status.upsert(
            {
                doc_id: {
                    "content_summary": f"[FAILED] {file_name}",
                    "content_length": 0,
                    "file_path": file_name,
                    "status": DocStatus.FAILED.value,
                    "created_at": now,
                    "updated_at": now,
                    "chunks_count": 0,
                    "error_msg": truncated_err,
                }
            }
        )
        logger.warning(
            "Recorded FAILED doc_status for %s (doc_id=%s): %s",
            file_name,
            doc_id,
            truncated_err,
        )
    except Exception as record_err:
        logger.error("Could not record failed doc_status for %s: %s", file_name, record_err)