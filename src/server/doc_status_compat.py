"""Compatibility shim for RAG-Anything -> LightRAG doc_status writes."""

from __future__ import annotations

import logging
from typing import Any

from lightrag.base import DocStatus

from src.utils.time_utils import to_local_iso

logger = logging.getLogger(__name__)

INCOMPATIBLE_FIELDS = {"multimodal_processed", "multimodal_content", "scheme_name"}
VALID_STATUSES = {
    DocStatus.PENDING.value,
    DocStatus.PROCESSING.value,
    DocStatus.PREPROCESSED.value,
    DocStatus.PROCESSED.value,
    DocStatus.FAILED.value,
}


def filter_doc_data(doc_data: dict[str, Any]) -> dict[str, Any]:
    """Drop fields LightRAG doc_status model does not accept."""
    return {key: value for key, value in doc_data.items() if key not in INCOMPATIBLE_FIELDS}


def normalize_doc_status(status: Any, doc_id: str) -> str:
    """Map RAG-Anything status values onto LightRAG's status enum."""
    status_value = status.value if hasattr(status, "value") else status
    if status_value == "handling":
        return DocStatus.PROCESSING.value
    if status_value == "parsing":
        return DocStatus.PROCESSING.value
    if status_value == "ready":
        return DocStatus.PENDING.value
    if status_value in VALID_STATUSES:
        return status_value

    logger.warning("Unknown status '%s' for doc %s, mapping to PROCESSING", status_value, doc_id)
    return DocStatus.PROCESSING.value


def localize_doc_timestamps(doc_data: dict[str, Any]) -> dict[str, Any]:
    """Convert UTC-ish LightRAG timestamps to local ISO strings for UI display."""
    localized = dict(doc_data)
    for field_name in ("created_at", "updated_at"):
        if localized.get(field_name):
            localized[field_name] = to_local_iso(localized[field_name])
    return localized


def apply_doc_status_compatibility_shim(lightrag_instance) -> None:
    """Wrap doc_status read/write methods with field filtering and status mapping."""
    doc_status = lightrag_instance.doc_status
    if getattr(doc_status, "_govcon_compat_shim_applied", False):
        return

    original_upsert = doc_status.upsert
    original_get_by_id = doc_status.get_by_id
    original_get_docs_paginated = doc_status.get_docs_paginated

    async def filtered_upsert(data: dict):
        filtered_data = {}
        for doc_id, raw_doc_data in data.items():
            filtered_doc_data = localize_doc_timestamps(filter_doc_data(raw_doc_data))
            if "status" in filtered_doc_data:
                filtered_doc_data["status"] = normalize_doc_status(filtered_doc_data["status"], doc_id)
            filtered_data[doc_id] = filtered_doc_data
        return await original_upsert(filtered_data)

    async def filtered_get_by_id(doc_id: str):
        result = await original_get_by_id(doc_id)
        if result and isinstance(result, dict):
            return filter_doc_data(result)
        return result

    async def filtered_get_docs_paginated(*args, **kwargs):
        result = await original_get_docs_paginated(*args, **kwargs)
        if result and isinstance(result, tuple) and len(result) >= 2:
            docs_with_ids, total_count = result[0], result[1]
            filtered_docs = []
            for doc_id, raw_doc_data in docs_with_ids:
                filtered_docs.append((doc_id, filter_doc_data(raw_doc_data)))
            return (filtered_docs, total_count), *result[2:]
        return result

    doc_status.upsert = filtered_upsert
    doc_status.get_by_id = filtered_get_by_id
    doc_status.get_docs_paginated = filtered_get_docs_paginated
    doc_status._govcon_compat_shim_applied = True