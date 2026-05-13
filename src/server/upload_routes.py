"""Upload endpoint registration for document ingestion."""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import File, Query, UploadFile
from fastapi.responses import JSONResponse

from src.server.evergreen_bootstrap import is_new_workspace, seed_evergreen_docs
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
    vault_store=None,
    evergreen_dir: Path | None = None,
):
    """Override LightRAG's WebUI /documents/upload endpoint to use RAG-Anything."""

    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

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
        vault_only: bool = Query(
            False,
            description="If true, store uploaded file as a vault note; skip KG extraction entirely.",
        ),
    ):
        logger.info(
            "🔔 ENDPOINT CALLED: /documents/upload with file: %s (stage_only=%s, vault_only=%s)",
            file.filename,
            stage_only,
            vault_only,
        )

        # ------------------------------------------------------------------
        # Vault-only path: create a knowledge note, skip KG extraction
        # ------------------------------------------------------------------
        if vault_only:
            from pathlib import Path
            from src.server.vault_store import VaultStore

            store = vault_store
            if store is None:
                from src.core.config import get_settings
                _vault_dir = Path(get_settings().vault_path).resolve()
                _vault_dir.mkdir(parents=True, exist_ok=True)
                store = VaultStore(vault_dir=_vault_dir, now=_now)

            try:
                content = (await file.read()).decode("utf-8", errors="replace")
            except Exception:
                content = ""

            create_kwargs = dict(
                title=file.filename or "Uploaded document",
                body=content,
                note_type="article",
                topic="",
                source=file.filename or "upload",
            )
            if workspace:
                create_kwargs["pursuit"] = workspace

            note = store.create(**create_kwargs)
            logger.info("📝 Vault note created for %s (id=%s)", file.filename, note["id"])
            return JSONResponse(
                {
                    "status": "vault",
                    "vault_note_id": note["id"],
                    "message": f"{file.filename} saved to vault",
                }
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
            # Detect new workspace BEFORE processing so the check is unambiguous.
            _new_ws = await is_new_workspace(rag_instance)

            processing_result = await process_document_func(
                str(file_path),
                file_path.name,
                rag_instance,
                rag_instance.llm_model_func,
            )

            # Evergreen bootstrap — seed on first upload only.
            if _new_ws:
                from src.core.config import get_settings
                _ev_dir = evergreen_dir or Path(get_settings().working_dir) / "_platform" / "evergreen"
                _ws_name = workspace or get_settings().workspace
                _ev_count = await seed_evergreen_docs(
                    rag_instance, _ev_dir, process_document_func, callback, workspace=_ws_name
                )
                if _ev_count:
                    logger.info("🌿 Seeded workspace '%s' with %d evergreen doc(s)", _ws_name, _ev_count)

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