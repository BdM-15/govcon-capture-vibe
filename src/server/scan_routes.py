"""Filesystem scan route and helpers for batch document ingestion."""

from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import BackgroundTasks, Query
from fastapi.responses import JSONResponse

from src.core import get_settings
from src.server.upload_staging import list_scannable_files, resolve_scan_folder

logger = logging.getLogger(__name__)

_ACTIVE_SCAN_STATUSES = frozenset(
    {
        "pending",
        "parsing",
        "analyzing",
        "processing",
        "preprocessed",
        "processed",
    }
)

_scan_lock = asyncio.Lock()
_active_scans: dict[str, str] = {}


def _scan_workspace_key(folder: Path) -> str:
    return folder.name


def _is_duplicate_status(record: dict[str, Any]) -> bool:
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    summary = str(record.get("content_summary") or "")
    return bool(metadata.get("is_duplicate")) or summary.startswith("[DUPLICATE:")


async def _existing_records_for_basename(doc_status: Any, basename: str) -> list[dict[str, Any]]:
    """Return all doc_status rows for a canonical basename."""
    records: list[dict[str, Any]] = []
    storage_data = getattr(doc_status, "_data", None)
    storage_lock = getattr(doc_status, "_storage_lock", None)
    if storage_data is not None:
        if storage_lock is None:
            items = list(storage_data.items())
        else:
            async with storage_lock:
                items = list(storage_data.items())
        for _doc_id, record in items:
            if isinstance(record, dict) and record.get("file_path") == basename:
                records.append(record)
        return records

    get_basename = getattr(doc_status, "get_doc_by_file_basename", None)
    if get_basename is not None:
        match = await get_basename(basename)
        if match:
            records.append(match[1])
            return records

    try:
        single = await doc_status.get_doc_by_file_path(basename)
    except Exception:
        single = None
    if single:
        records.append(single)
    return records


def _should_skip_for_scan(
    records: list[dict[str, Any]],
    *,
    in_upload_queue: bool,
) -> bool:
    if in_upload_queue:
        return True
    if not records:
        return False

    statuses = {str(record.get("status") or "").lower() for record in records}
    if statuses & _ACTIVE_SCAN_STATUSES:
        return True

    if any(
        str(record.get("status") or "").lower() == "failed" and not _is_duplicate_status(record)
        for record in records
    ):
        return False

    if any(_is_duplicate_status(record) for record in records):
        return True

    return bool(statuses)


async def _try_acquire_scan(workspace_key: str, track_id: str) -> str | None:
    async with _scan_lock:
        return _active_scans.get(workspace_key)


async def _register_scan(workspace_key: str, track_id: str) -> None:
    async with _scan_lock:
        _active_scans[workspace_key] = track_id


async def _release_scan(workspace_key: str, track_id: str) -> None:
    async with _scan_lock:
        if _active_scans.get(workspace_key) == track_id:
            _active_scans.pop(workspace_key, None)


async def filter_already_processed(
    rag_instance,
    files: list[Path],
    *,
    callback: Any | None = None,
) -> tuple[list[Path], list[str]]:
    """Split files into (to_process, skipped_names) using doc_status and upload queue."""
    to_process: list[Path] = []
    skipped: list[str] = []
    doc_status = rag_instance.lightrag.doc_status
    pending_uploads: set[str] = set()
    if callback is not None:
        with callback.lock:
            pending_uploads = set(callback.pending_uploads)

    for file_path in files:
        basename = file_path.name
        try:
            records = await _existing_records_for_basename(doc_status, basename)
        except Exception:
            records = []
        if _should_skip_for_scan(
            records,
            in_upload_queue=basename in pending_uploads,
        ):
            skipped.append(basename)
        else:
            to_process.append(file_path)
    return to_process, skipped


async def run_scan(
    rag_instance,
    folder: Path,
    track_id: str,
    *,
    process_document_func,
    callback,
    workspace_key: str,
) -> None:
    """Background task: process all new files in folder sequentially."""
    try:
        all_files = list_scannable_files(folder)
        if not all_files:
            logger.info("📭 [scan %s] No supported files in %s", track_id, folder)
            return

        to_process, skipped = await filter_already_processed(
            rag_instance,
            all_files,
            callback=callback,
        )
        logger.info(
            "📂 [scan %s] %s: %d found, %d to process, %d skipped (processed/in-flight/duplicate)",
            track_id,
            folder,
            len(all_files),
            len(to_process),
            len(skipped),
        )

        if not to_process:
            return

        for file_path in to_process:
            await callback.register_request_start(file_path.name)
            try:
                logger.info("📄 [scan %s] Processing %s", track_id, file_path.name)
                await process_document_func(
                    str(file_path),
                    file_path.name,
                    rag_instance,
                    rag_instance.llm_model_func,
                )
            except Exception as exc:
                logger.error("❌ [scan %s] Failed %s: %s", track_id, file_path.name, exc)
            finally:
                await callback.register_request_end(file_path.name)

        logger.info(
            "✅ [scan %s] Completed — %d files queued. Batch post-processing will run after %ss idle.",
            track_id,
            len(to_process),
            get_settings().batch_timeout_seconds,
        )
    except Exception as exc:
        logger.error("❌ [scan %s] Scan failed: %s", track_id, exc)
        logger.error(traceback.format_exc())
    finally:
        await _release_scan(workspace_key, track_id)


def create_scan_endpoint(
    app,
    rag_instance,
    *,
    process_document_func,
    callback,
):
    """Register POST /scan-rfp — filesystem batch ingest from inputs/<workspace>/."""

    async def scan_rfp(
        background_tasks: BackgroundTasks,
        workspace: Optional[str] = Query(
            None,
            description="Workspace to scan. Defaults to the server's current workspace.",
        ),
    ):
        try:
            folder = resolve_scan_folder(workspace)
            workspace_key = _scan_workspace_key(folder)
            files = list_scannable_files(folder)
            track_id = f"scan-{uuid.uuid4().hex[:8]}"

            if not files:
                return JSONResponse(
                    {
                        "status": "empty",
                        "track_id": track_id,
                        "folder": str(folder),
                        "files_found": 0,
                        "message": (
                            f"No supported files found in {folder}. "
                            "Drop PDFs/DOCX/etc. into this folder and call /scan-rfp again."
                        ),
                    }
                )

            active_track = await _try_acquire_scan(workspace_key, track_id)
            if active_track:
                return JSONResponse(
                    {
                        "status": "scan_already_running",
                        "track_id": active_track,
                        "folder": str(folder),
                        "files_found": len(files),
                        "message": (
                            f"Scan already in progress for {workspace_key} "
                            f"(track_id={active_track}). "
                            "Wait for it to finish before starting another scan."
                        ),
                    }
                )

            await _register_scan(workspace_key, track_id)
            background_tasks.add_task(
                run_scan,
                rag_instance,
                folder,
                track_id,
                process_document_func=process_document_func,
                callback=callback,
                workspace_key=workspace_key,
            )

            return JSONResponse(
                {
                    "status": "scanning_started",
                    "track_id": track_id,
                    "folder": str(folder),
                    "files_found": len(files),
                    "message": (
                        f"Scanning {len(files)} file(s) in background. "
                        f"Watch server logs (filter on '[scan {track_id}]') for progress. "
                        "Processed, in-flight, and duplicate files are skipped automatically."
                    ),
                }
            )
        except Exception as exc:
            logger.error("❌ /scan-rfp failed: %s", exc)
            return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)

    app.add_api_route(
        "/scan-rfp",
        scan_rfp,
        methods=["POST"],
        response_class=JSONResponse,
    )