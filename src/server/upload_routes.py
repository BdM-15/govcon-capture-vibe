"""Upload endpoint registration for document ingestion."""

from __future__ import annotations

import logging
import traceback
from typing import Optional

from fastapi import File, Query, UploadFile
from fastapi.responses import JSONResponse

from src.server.upload_staging import save_upload_to_workspace

logger = logging.getLogger(__name__)


def create_insert_endpoint(
    app,
    rag_instance,
    *,
    process_document_func,
    callback,
):
    """Create custom /insert endpoint with automatic semantic post-processing."""

    async def insert_with_semantic_processing(
        file: UploadFile = File(...),
        workspace: Optional[str] = Query(
            None,
            description="Workspace to save into. Defaults to the server's current workspace.",
        ),
    ):
        logger.info("🔔 ENDPOINT CALLED: /insert with file: %s", file.filename)
        await callback.register_request_start(file.filename)

        try:
            file_path = await save_upload_to_workspace(file, workspace)
            logger.info("📄 Processing %s via /insert (saved to %s)", file_path.name, file_path.parent)

            processing_result = await process_document_func(
                str(file_path),
                file_path.name,
                rag_instance,
                rag_instance.llm_model_func,
            )

            logger.info("✅ Processing complete for %s", file_path.name)
            return JSONResponse(
                {
                    "status": "success",
                    "message": f"Document {file_path.name} processed successfully",
                    "saved_to": str(file_path),
                    "relationships_inferred": processing_result["relationships_inferred"],
                    "method": "RAG-Anything + LLM semantic inference (format-agnostic)",
                }
            )
        except Exception as exc:
            logger.error("❌ Error processing document: %s", exc)
            logger.error(traceback.format_exc())
            return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)
        finally:
            await callback.register_request_end(file.filename)

    app.add_api_route(
        "/insert",
        insert_with_semantic_processing,
        methods=["POST"],
        response_class=JSONResponse,
    )


def create_documents_upload_endpoint(
    app,
    rag_instance,
    *,
    process_document_func,
    callback,
):
    """Override LightRAG's WebUI /documents/upload endpoint to use RAG-Anything."""

    async def documents_upload_with_raganything(
        file: UploadFile = File(...),
        workspace: Optional[str] = Query(
            None,
            description="Workspace to save into. Defaults to the server's current workspace.",
        ),
        stage_only: bool = Query(
            False,
            description="If true, save the file to inputs/<workspace>/ without triggering extraction. Use Folder Watcher → Scan now to process later.",
        ),
    ):
        logger.info(
            "🔔 ENDPOINT CALLED: /documents/upload with file: %s (stage_only=%s)",
            file.filename,
            stage_only,
        )

        if not stage_only:
            await callback.register_request_start(file.filename)

        try:
            file_path = await save_upload_to_workspace(file, workspace)

            if stage_only:
                logger.info("📥 Staged %s to %s (no processing — awaiting /scan-rfp)", file_path.name, file_path.parent)
                return JSONResponse(
                    {
                        "status": "staged",
                        "message": f"Document {file_path.name} staged for batch scan",
                        "saved_to": str(file_path),
                        "stage_only": True,
                    }
                )

            logger.info(
                "📄 Processing %s via WebUI /documents/upload (saved to %s)",
                file_path.name,
                file_path.parent,
            )
            processing_result = await process_document_func(
                str(file_path),
                file_path.name,
                rag_instance,
                rag_instance.llm_model_func,
            )

            logger.info("✅ Processing complete for %s", file_path.name)
            return JSONResponse(
                {
                    "status": "success",
                    "message": f"Document {file_path.name} processed successfully",
                    "saved_to": str(file_path),
                    "relationships_inferred": processing_result.get("relationships_inferred", 0),
                    "method": "RAG-Anything + LLM semantic inference (format-agnostic)",
                }
            )
        except Exception as exc:
            logger.error("❌ Error processing document: %s", exc)
            logger.error(traceback.format_exc())
            return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)
        finally:
            if not stage_only:
                await callback.register_request_end(file.filename)

    app.add_api_route(
        "/documents/upload",
        documents_upload_with_raganything,
        methods=["POST"],
        response_class=JSONResponse,
    )