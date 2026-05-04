"""Filesystem scan route and helpers for batch document ingestion."""

from __future__ import annotations

import logging
import traceback
import uuid
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Query
from fastapi.responses import JSONResponse

from src.core import get_settings
from src.server.upload_staging import list_scannable_files, resolve_scan_folder

logger = logging.getLogger(__name__)


async def filter_already_processed(rag_instance, files: list[Path]) -> tuple[list[Path], list[str]]:
    """Split files into (to_process, already_processed_names) using doc_status."""
    to_process: list[Path] = []
    already: list[str] = []
    doc_status = rag_instance.lightrag.doc_status
    for file_path in files:
        try:
            existing = await doc_status.get_doc_by_file_path(file_path.name)
        except Exception:
            existing = None
        if existing and existing.get("status") == "processed":
            already.append(file_path.name)
        else:
            to_process.append(file_path)
    return to_process, already


async def run_scan(
    rag_instance,
    folder: Path,
    track_id: str,
    *,
    process_document_func,
    callback,
) -> None:
    """Background task: process all new files in folder sequentially."""
    try:
        all_files = list_scannable_files(folder)
        if not all_files:
            logger.info("📭 [scan %s] No supported files in %s", track_id, folder)
            return

        to_process, already = await filter_already_processed(rag_instance, all_files)
        logger.info(
            "📂 [scan %s] %s: %d found, %d to process, %d already processed",
            track_id,
            folder,
            len(all_files),
            len(to_process),
            len(already),
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

            background_tasks.add_task(
                run_scan,
                rag_instance,
                folder,
                track_id,
                process_document_func=process_document_func,
                callback=callback,
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
                        "Already-processed files are skipped automatically."
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