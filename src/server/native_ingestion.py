"""Native LightRAG document ingestion helpers."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from lightrag.constants import (
    FULL_DOCS_FORMAT_PENDING_PARSE,
    PARSER_ENGINE_LEGACY,
)
from lightrag.parser.routing import resolve_file_parser_directives
from lightrag.utils import compute_mdhash_id

from src.core import get_settings
from src.server.document_processing import record_failed_doc

logger = logging.getLogger(__name__)


PipelineEnqueueFile = Callable[..., Awaitable[tuple[bool, str]]]


TEXT_BEARING_TABLE_SUFFIXES = {
    ".csv",
    ".doc",
    ".docx",
    ".md",
    ".txt",
    ".xls",
    ".xlsm",
    ".xlsx",
    ".tsv",
}

LIGHTRAG_FILE_PIPELINE_SUFFIXES = {".xlsx"}


def _new_track_id(file_name: str) -> str:
    stem = Path(file_name).stem or "document"
    safe_stem = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem)[:48]
    return f"native-{safe_stem}-{uuid.uuid4().hex[:8]}"


def _suppress_text_bearing_table_analysis(file_name: str, process_options: str) -> str:
    suffix = Path(file_name).suffix.lower()
    if suffix not in TEXT_BEARING_TABLE_SUFFIXES:
        return process_options
    return "".join(option for option in process_options if option != "t")


def resolve_govcon_parser_directives(file_name: str) -> tuple[str, str]:
    if Path(file_name).suffix.lower() in LIGHTRAG_FILE_PIPELINE_SUFFIXES:
        return PARSER_ENGINE_LEGACY, ""
    parser_rules = get_settings().lightrag_parser
    parser_engine, process_options = resolve_file_parser_directives(
        file_name,
        parser_rules=parser_rules,
        require_external_endpoint=False,
    )
    return parser_engine, _suppress_text_bearing_table_analysis(
        file_name, process_options
    )


def _uses_lightrag_file_pipeline(file_name: str) -> bool:
    return Path(file_name).suffix.lower() in LIGHTRAG_FILE_PIPELINE_SUFFIXES


def _load_lightrag_pipeline_enqueue_file() -> PipelineEnqueueFile:
    try:
        from lightrag.api.routers.document_routes import pipeline_enqueue_file
    except SystemExit as exc:
        raise RuntimeError(
            "LightRAG's file upload pipeline could not be imported after API "
            "configuration. Initialize the LightRAG API app before processing XLSX."
        ) from exc
    except Exception as exc:  # pragma: no cover - import failure depends on LightRAG packaging
        raise RuntimeError("Unable to import LightRAG's file upload pipeline") from exc

    return pipeline_enqueue_file


async def _enqueue_with_lightrag_file_pipeline(
    lightrag: Any,
    file_path: str,
    track_id: str,
    *,
    from_scan: bool,
    pipeline_enqueue_file_fn: PipelineEnqueueFile | None = None,
) -> str:
    enqueue_file = pipeline_enqueue_file_fn or _load_lightrag_pipeline_enqueue_file()
    success, returned_track_id = await enqueue_file(
        lightrag,
        Path(file_path),
        track_id,
        from_scan=from_scan,
    )
    if not success:
        raise RuntimeError(
            f"LightRAG file enqueue failed for {Path(file_path).name}; "
            "see document status and server logs for extractor details."
        )
    return returned_track_id or track_id


def _status_value(status: Any) -> str:
    return str(getattr(status, "value", status) or "").lower()


def _is_retryable_failed_status(record: dict[str, Any]) -> bool:
    return _status_value(record.get("status")) == "failed"


def _status_field(record: Any, field_name: str) -> Any:
    if isinstance(record, dict):
        return record.get(field_name)
    return getattr(record, field_name, None)


def _is_duplicate_status(record: Any) -> bool:
    metadata = _status_field(record, "metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    summary = str(_status_field(record, "content_summary") or "")
    return bool(metadata.get("is_duplicate")) or summary.startswith("[DUPLICATE:")


async def _matching_failed_status_ids(doc_status: Any, file_name: str) -> list[str]:
    storage_data = getattr(doc_status, "_data", None)
    storage_lock = getattr(doc_status, "_storage_lock", None)
    if storage_data is not None:
        records: list[tuple[str, dict[str, Any]]] = []
        if storage_lock is None:
            records = list(storage_data.items())
        else:
            async with storage_lock:
                records = list(storage_data.items())
        return [
            doc_id
            for doc_id, record in records
            if isinstance(record, dict)
            and record.get("file_path") == file_name
            and _is_retryable_failed_status(record)
        ]

    get_by_basename = getattr(doc_status, "get_doc_by_file_basename", None)
    if get_by_basename is None:
        return []
    match = await get_by_basename(file_name)
    if not match:
        return []
    doc_id, record = match
    if isinstance(record, dict) and _is_retryable_failed_status(record):
        return [doc_id]
    return []


async def _clear_retryable_failed_statuses(lightrag: Any, file_name: str) -> list[str]:
    doc_status = getattr(lightrag, "doc_status", None)
    delete_status = getattr(doc_status, "delete", None)
    if doc_status is None or delete_status is None:
        return []

    failed_ids = await _matching_failed_status_ids(doc_status, file_name)
    if not failed_ids:
        return []

    await delete_status(failed_ids)
    index_done = getattr(doc_status, "index_done_callback", None)
    if index_done is not None:
        await index_done()
    logger.info(
        "Cleared %s retryable failed native doc_status record(s) for %s",
        len(failed_ids),
        file_name,
    )
    return failed_ids


async def _native_track_failures(lightrag: Any, track_id: str) -> list[tuple[str, str]]:
    doc_status = getattr(lightrag, "doc_status", None)
    get_by_track = getattr(doc_status, "get_docs_by_track_id", None)
    if get_by_track is None:
        return []

    track_docs = await get_by_track(track_id)
    failures: list[tuple[str, str]] = []
    for doc_id, record in (track_docs or {}).items():
        if _status_value(_status_field(record, "status")) != "failed":
            continue
        if _is_duplicate_status(record):
            continue
        error = str(_status_field(record, "error_msg") or "native pipeline failed")
        failures.append((doc_id, error))
    return failures


async def process_document_with_native_ingestion(
    file_path: str,
    file_name: str,
    rag_instance: Any,
    llm_func: Any | None = None,
    *,
    track_id: str | None = None,
    from_scan: bool = False,
    callback: Any | None = None,
    pipeline_enqueue_file_fn: PipelineEnqueueFile | None = None,
) -> dict[str, Any]:
    """Queue one source document through LightRAG's native parser pipeline."""

    del llm_func
    lightrag = rag_instance.lightrag
    resolved_track_id = track_id or _new_track_id(file_name)
    parser_engine, process_options = resolve_govcon_parser_directives(
        file_name or file_path
    )
    doc_id = compute_mdhash_id(Path(file_name or file_path).name, prefix="doc-")
    start_time = time.perf_counter()

    try:
        logger.info(
            "📄 Native LightRAG ingest %s (engine=%s options=%s track=%s)",
            file_name,
            parser_engine,
            process_options or "default",
            resolved_track_id,
        )
        source_name = Path(file_name or file_path).name
        await _clear_retryable_failed_statuses(lightrag, source_name)
        if _uses_lightrag_file_pipeline(source_name):
            resolved_track_id = await _enqueue_with_lightrag_file_pipeline(
                lightrag,
                file_path,
                resolved_track_id,
                from_scan=from_scan,
                pipeline_enqueue_file_fn=pipeline_enqueue_file_fn,
            )
        else:
            await lightrag.apipeline_enqueue_documents(
                "",
                file_paths=file_path,
                track_id=resolved_track_id,
                docs_format=FULL_DOCS_FORMAT_PENDING_PARSE,
                parse_engine=parser_engine,
                process_options=process_options,
                from_scan=from_scan,
            )
        await lightrag.apipeline_process_enqueue_documents()
        failures = await _native_track_failures(lightrag, resolved_track_id)
        if failures:
            detail = "; ".join(f"{doc_id}: {error}" for doc_id, error in failures)
            raise RuntimeError(f"Native LightRAG pipeline failed for {file_name}: {detail}")
        if callback is not None:
            callback.on_document_complete(
                file_path=file_path,
                doc_id=doc_id,
                duration_seconds=time.perf_counter() - start_time,
            )
        return {
            "status": "success",
            "relationships_inferred": 0,
            "method": "native_lightrag_pipeline",
            "message": "Document queued and processed by LightRAG native pipeline.",
            "track_id": resolved_track_id,
            "workspace": getattr(lightrag, "workspace", ""),
        }
    except Exception as exc:
        await record_failed_doc(
            rag_instance,
            file_path,
            Path(file_name or file_path).name,
            doc_id,
            str(exc),
        )
        if callback is not None:
            callback.on_document_error(
                file_path=file_path,
                doc_id=doc_id,
                error=str(exc),
            )
        raise
