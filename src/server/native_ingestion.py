"""Native LightRAG document ingestion helpers."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from lightrag.constants import FULL_DOCS_FORMAT_PENDING_PARSE
from lightrag.parser.routing import resolve_file_parser_directives
from lightrag.utils import compute_mdhash_id

from src.server.document_processing import record_failed_doc

logger = logging.getLogger(__name__)


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
    parser_engine, process_options = resolve_file_parser_directives(
        file_name,
        require_external_endpoint=False,
    )
    return parser_engine, _suppress_text_bearing_table_analysis(file_name, process_options)


async def process_document_with_native_ingestion(
    file_path: str,
    file_name: str,
    rag_instance: Any,
    llm_func: Any | None = None,
    *,
    track_id: str | None = None,
    from_scan: bool = False,
) -> dict[str, Any]:
    """Queue one source document through LightRAG's native parser pipeline."""

    del llm_func
    lightrag = rag_instance.lightrag
    resolved_track_id = track_id or _new_track_id(file_name)
    parser_engine, process_options = resolve_govcon_parser_directives(file_name or file_path)
    doc_id = compute_mdhash_id(Path(file_name or file_path).name, prefix="doc-")

    try:
        logger.info(
            "📄 Native LightRAG ingest %s (engine=%s options=%s track=%s)",
            file_name,
            parser_engine,
            process_options or "default",
            resolved_track_id,
        )
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
        raise