"""Run, artifact, chunk-preview, and Studio routes for skill UI."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from src.core import get_settings
from src.skills import get_skill_manager
from src.skills.runs import resolve_artifact_mime

logger = logging.getLogger(__name__)


def register_skill_run_ui_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
) -> None:
    """Register skill run, artifact, chunk-preview, and Studio endpoints."""

    @app.get("/api/ui/skills/{name}/runs", tags=["theseus-ui"])
    async def list_skill_runs_route(name: str, limit: int = 50) -> JSONResponse:
        mgr = get_skill_manager()
        runs = mgr.list_runs(workspace_dir(), skill_name=name, limit=limit)
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "skill": name,
                "runs": runs,
            }
        )

    @app.get("/api/ui/skills/{name}/runs/{run_id}", tags=["theseus-ui"])
    async def get_skill_run_route(name: str, run_id: str) -> JSONResponse:
        mgr = get_skill_manager()
        run = mgr.get_run(workspace_dir(), name, run_id)
        if run is None:
            raise HTTPException(404, f"Unknown run: {name}/{run_id}")
        return JSONResponse(run)

    @app.get(
        "/api/ui/skills/{name}/runs/{run_id}/reasoning",
        tags=["theseus-ui"],
    )
    async def get_skill_run_reasoning_route(name: str, run_id: str) -> JSONResponse:
        from src.skills.reasoning import build_reasoning_view

        mgr = get_skill_manager()
        run = mgr.get_run(workspace_dir(), name, run_id)
        if run is None:
            raise HTTPException(404, f"Unknown run: {name}/{run_id}")
        transcript = run.get("transcript") or []
        view = await asyncio.to_thread(build_reasoning_view, transcript)
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "skill": name,
                "run_id": run_id,
                "title": (run.get("metadata") or {}).get("title"),
                "created_at": (run.get("metadata") or {}).get("created_at"),
                "artifacts": run.get("artifacts") or [],
                **view,
            }
        )

    @app.get("/api/ui/chunks/{chunk_id}", tags=["theseus-ui"])
    async def get_chunk_route(chunk_id: str) -> JSONResponse:
        if not chunk_id or len(chunk_id) > 128 or "/" in chunk_id or "\\" in chunk_id:
            raise HTTPException(400, "Invalid chunk id")

        chunks_path = workspace_dir() / "kv_store_text_chunks.json"
        if not chunks_path.exists():
            raise HTTPException(404, "No text-chunk store in this workspace")

        def _load_chunk() -> Optional[dict]:
            try:
                store = json.loads(chunks_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed reading text-chunk store: %s", exc)
                return None
            return store.get(chunk_id)

        chunk = await asyncio.to_thread(_load_chunk)
        if not chunk:
            raise HTTPException(404, f"Unknown chunk: {chunk_id}")

        content = chunk.get("content") or chunk.get("text") or ""
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "chunk_id": chunk_id,
                "file_path": chunk.get("file_path") or chunk.get("full_doc_id"),
                "full_doc_id": chunk.get("full_doc_id"),
                "chunk_order_index": chunk.get("chunk_order_index"),
                "tokens": chunk.get("tokens"),
                "length": len(content),
                "content": content,
            }
        )

    @app.delete("/api/ui/skills/{name}/runs/{run_id}", tags=["theseus-ui"])
    async def delete_skill_run_route(name: str, run_id: str) -> JSONResponse:
        mgr = get_skill_manager()
        ok = mgr.delete_run(workspace_dir(), name, run_id)
        if not ok:
            raise HTTPException(404, f"Unknown or unsafe run id: {name}/{run_id}")
        return JSONResponse({"removed": run_id})

    @app.get(
        "/api/ui/skills/{name}/runs/{run_id}/artifacts/{filename}",
        tags=["theseus-ui"],
    )
    async def download_skill_run_artifact_route(
        name: str,
        run_id: str,
        filename: str,
    ) -> FileResponse:
        mgr = get_skill_manager()
        path = mgr.get_artifact_path(workspace_dir(), name, run_id, filename)
        if path is None:
            raise HTTPException(404, f"Artifact not found: {name}/{run_id}/{filename}")
        return FileResponse(
            path,
            media_type=resolve_artifact_mime(path.name),
            filename=path.name,
        )

    @app.get("/api/ui/studio", tags=["theseus-ui"])
    async def list_studio_deliverables_route(limit: int = 500) -> JSONResponse:
        mgr = get_skill_manager()
        deliverables = await asyncio.to_thread(
            mgr.list_deliverables,
            workspace_dir(),
            limit,
        )
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "count": len(deliverables),
                "deliverables": deliverables,
            }
        )