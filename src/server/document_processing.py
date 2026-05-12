"""Document ingest pipeline and doc_status repair helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Optional

from lightrag.base import DocStatus
from lightrag.utils import compute_mdhash_id

from src.core import get_settings
from src.utils.time_utils import now_local_iso

logger = logging.getLogger(__name__)


DISCARDED_CONTENT_TYPES = {
    "discarded",
    "header",
    "footer",
    "page_number",
    "aside_text",
    "page_footnote",
}


@dataclass
class ModalRebalanceStats:
    """Counts for local content-list modal artifact rebalancing."""

    tables_converted: int = 0
    lists_converted: int = 0
    seals_discarded: int = 0
    multimodal_kept: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.tables_converted or self.lists_converted or self.seals_discarded)


class _TableTextParser(HTMLParser):
    """Extract readable rows/cells from MinerU HTML table bodies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"}:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            text = " ".join(data.split())
            if text:
                self._current_cell.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._current_row is not None:
            cell_text = " ".join(self._current_cell or []).strip()
            self._current_row.append(cell_text)
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if any(cell.strip() for cell in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = None

    def to_text(self) -> str:
        return "\n".join(" | ".join(cell for cell in row if cell).strip() for row in self.rows).strip()


def _join_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _table_body_to_text(table_body: Any) -> str:
    body = _join_text(table_body)
    if not body:
        return ""
    if "<table" not in body.lower():
        return " ".join(body.split())

    parser = _TableTextParser()
    parser.feed(body)
    parsed = parser.to_text()
    return parsed or " ".join(body.split())


def _build_table_text_block(block: dict[str, Any]) -> str:
    caption = _join_text(block.get("table_caption"))
    body = _table_body_to_text(block.get("table_body"))
    footnote = _join_text(block.get("table_footnote"))
    parts = ["[TABLE]"]
    if caption:
        parts.append(f"Caption: {caption}")
    if body:
        parts.append(body)
    if footnote:
        parts.append(f"Footnote: {footnote}")
    parts.append("[/TABLE]")
    return "\n".join(parts)


def _build_list_text_block(block: dict[str, Any]) -> str:
    items = _join_text(block.get("list_items")) or _join_text(block.get("text"))
    if not items:
        return ""
    return f"[LIST]\n{items}\n[/LIST]"


def rebalance_modal_content_blocks(content_list: list[dict]) -> tuple[list[dict], ModalRebalanceStats]:
    """Convert text-bearing MinerU modal blocks to text and drop seal artifacts.

    RAG-Anything treats every non-text block as a multimodal chunk, then runs a
    second extraction pass that can over-amplify textual tables/lists. If MinerU
    already extracted the text, feed it through the normal LightRAG text path.
    """
    stats = ModalRebalanceStats()
    rebalanced: list[dict] = []

    for block in content_list:
        block_type = block.get("type")
        if block_type == "seal":
            stats.seals_discarded += 1
            continue

        if block_type == "table":
            text = _build_table_text_block(block)
            if text.strip() != "[TABLE]\n[/TABLE]":
                converted = dict(block)
                converted["type"] = "text"
                converted["text"] = text
                converted["original_type"] = "table"
                converted["modal_rebalanced"] = True
                rebalanced.append(converted)
                stats.tables_converted += 1
                continue

        if block_type == "list":
            text = _build_list_text_block(block)
            if text:
                converted = dict(block)
                converted["type"] = "text"
                converted["text"] = text
                converted["original_type"] = "list"
                converted["modal_rebalanced"] = True
                rebalanced.append(converted)
                stats.lists_converted += 1
                continue

        if block_type != "text":
            stats.multimodal_kept += 1
        rebalanced.append(block)

    return rebalanced, stats


def filter_discarded_content_blocks(content_list: list[dict]) -> tuple[list[dict], int]:
    """Drop MinerU content types we intentionally ignore downstream."""
    filtered_content = [
        item for item in content_list if item.get("type") not in DISCARDED_CONTENT_TYPES
    ]
    return filtered_content, len(content_list) - len(filtered_content)


def summarize_processed_content(file_name: str, filtered_content: list[dict]) -> tuple[str, int]:
    """Build doc_status summary and content length for processed docs."""
    for block in filtered_content:
        if block.get("type") != "text":
            continue
        text = (block.get("text") or "").strip()
        if text:
            return text[:200], sum(len((b.get("text") or "")) for b in filtered_content)

    type_counts: dict[str, int] = {}
    for block in filtered_content:
        block_type = block.get("type", "unknown")
        type_counts[block_type] = type_counts.get(block_type, 0) + 1
    breakdown = ", ".join(f"{count} {block_type}" for block_type, count in sorted(type_counts.items()))
    summary = f"[NON-TEXT] {file_name} ({breakdown})"
    return summary, sum(len((b.get("text") or "")) for b in filtered_content)


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
            "📛 Recorded FAILED doc_status for %s (doc_id=%s): %s",
            file_name,
            doc_id,
            truncated_err,
        )
    except Exception as record_err:
        logger.error("⚠️  Could not record failed doc_status for %s: %s", file_name, record_err)


async def ensure_doc_status_processed(
    rag_instance,
    file_name: str,
    doc_id: Optional[str],
    filtered_content: list[dict],
    duration_seconds: float,
) -> None:
    """Backfill processed doc_status row when non-text docs bypass standard tracking."""
    if not doc_id:
        return
    try:
        existing = await rag_instance.lightrag.doc_status.get_by_id(doc_id)
        if existing:
            return

        summary, content_length = summarize_processed_content(file_name, filtered_content)
        now = now_local_iso()
        await rag_instance.lightrag.doc_status.upsert(
            {
                doc_id: {
                    "content_summary": summary,
                    "content_length": content_length,
                    "file_path": file_name,
                    "status": DocStatus.PROCESSED.value,
                    "created_at": now,
                    "updated_at": now,
                    "chunks_count": len(filtered_content),
                    "metadata": {
                        "backfilled": True,
                        "reason": "tabular_or_image_only",
                        "duration_seconds": round(duration_seconds, 2),
                    },
                }
            }
        )
        logger.info(
            "📝 Backfilled PROCESSED doc_status for %s (doc_id=%s, blocks=%d) — non-text content bypassed standard tracking",
            file_name,
            doc_id,
            len(filtered_content),
        )
    except Exception as backfill_err:
        logger.error("⚠️  Could not backfill doc_status for %s: %s", file_name, backfill_err)


async def process_document_with_semantic_inference(
    file_path: str,
    file_name: str,
    rag_instance,
    llm_func,
    *,
    callback,
) -> dict:
    """Integrated document processing with semantic relationship inference."""
    logger.info("📄 Processing %s", file_name)

    settings = get_settings()
    mineru_backend = settings.mineru_backend
    start_time = datetime.now()
    doc_id: Optional[str] = None

    try:
        content_list, doc_id = await rag_instance.parse_document(
            file_path=file_path,
            parse_method="auto",
            backend=mineru_backend,
        )

        parse_duration = (datetime.now() - start_time).total_seconds()
        rag_instance.callback_manager.dispatch(
            "on_parse_complete",
            file_path=file_path,
            content_blocks=len(content_list),
            doc_id=doc_id,
            duration_seconds=parse_duration,
        )

        filtered_content, discarded_count = filter_discarded_content_blocks(content_list)
        if discarded_count > 0:
            logger.info(
                "🚫 Filtered %d discarded content blocks (keeping %d/%d)",
                discarded_count,
                len(filtered_content),
                len(content_list),
            )

        rebalanced_content, rebalance_stats = rebalance_modal_content_blocks(filtered_content)
        if rebalance_stats.changed:
            logger.info(
                "⚖️ Rebalanced modal artifacts before insertion: %d tables -> text, %d lists -> text, %d seals discarded, %d multimodal kept",
                rebalance_stats.tables_converted,
                rebalance_stats.lists_converted,
                rebalance_stats.seals_discarded,
                rebalance_stats.multimodal_kept,
            )

        llm_timeout = settings.llm_timeout
        logger.info("🚀 Using RAG-Anything native end-to-end pipeline")
        logger.info("   Ontology: 33 govcon entity types | Timeout: %ss", llm_timeout)

        await rag_instance.insert_content_list(
            content_list=rebalanced_content,
            file_path=file_path,
            doc_id=doc_id,
        )

        total_duration = (datetime.now() - start_time).total_seconds()
        logger.info("✅ RAG-Anything processing complete")

        await ensure_doc_status_processed(
            rag_instance,
            file_name,
            doc_id,
            rebalanced_content,
            total_duration,
        )

        rag_instance.callback_manager.dispatch(
            "on_document_complete",
            file_path=file_path,
            doc_id=doc_id,
            duration_seconds=total_duration,
        )

        stats = await callback.get_stats()
        logger.info(
            "⏭️  Queue: %s processing, %s completed",
            stats["processing"],
            stats["completed"],
        )

        return {
            "status": "success",
            "relationships_inferred": 0,
            "method": "native_rag_anything",
            "message": "✅ Document processed via RAG-Anything native pipeline.",
        }
    except Exception as exc:
        await record_failed_doc(rag_instance, file_path, file_name, doc_id, str(exc))
        rag_instance.callback_manager.dispatch(
            "on_document_error",
            file_path=file_path,
            doc_id=doc_id,
            error=str(exc),
        )
        raise