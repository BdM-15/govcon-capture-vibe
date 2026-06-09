"""Thin HTTP adapters for Capture Studio deliverable lifecycle."""

from __future__ import annotations

import asyncio
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Type

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from src.core import get_settings
from src.skills.run_metadata import resolve_artifact_mime
from src.skills.runs import SkillRunStore


class StudioArtifactRef(BaseModel):
    """One Studio artifact reference (skill + run + filename)."""

    skill: str = Field(..., min_length=1, max_length=128)
    run_id: str = Field(..., min_length=1, max_length=128)
    filename: str = Field(..., min_length=1, max_length=255)


class StudioArtifactDeletePayload(BaseModel):
    """Bulk deletion request for Studio artifacts."""

    artifacts: list[StudioArtifactRef] = Field(..., min_length=1, max_length=200)


class StudioArtifactZipPayload(BaseModel):
    """Bulk download request for Studio artifacts."""

    artifacts: list[StudioArtifactRef] = Field(..., min_length=1, max_length=200)


class StudioTrashRestoreItem(BaseModel):
    """One trashed artifact selected for restore."""

    trash_id: str = Field(..., min_length=1, max_length=255)


class StudioTrashRestorePayload(BaseModel):
    """Bulk restore request for trashed Studio artifacts."""

    artifacts: list[StudioTrashRestoreItem] = Field(..., min_length=1, max_length=200)


def _zip_segment(value: str, fallback: str) -> str:
    cleaned = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in value.strip()
    ).strip("._")
    return (cleaned[:96] or fallback)


def register_studio_ui_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
    run_store_factory: Type[SkillRunStore] = SkillRunStore,
) -> None:
    """Register Studio deliverable, trash, and bulk-download endpoints."""

    @app.get("/api/ui/studio", tags=["theseus-ui"])
    async def list_studio_deliverables_route(limit: int = 500) -> JSONResponse:
        store = run_store_factory()
        deliverables = await asyncio.to_thread(
            store.list_deliverables,
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

    @app.get("/api/ui/studio/trash", tags=["theseus-ui"])
    async def list_studio_trash_route(limit: int = 200) -> JSONResponse:
        store = run_store_factory()
        artifacts = await asyncio.to_thread(
            store.list_trashed_artifacts,
            workspace_dir(),
            limit=limit,
        )
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "count": len(artifacts),
                "artifacts": artifacts,
            }
        )

    @app.post("/api/ui/studio/artifacts.zip", tags=["theseus-ui"])
    async def zip_studio_artifacts_route(
        payload: StudioArtifactZipPayload = Body(...),
    ) -> Response:
        store = run_store_factory()
        refs = [item.model_dump() for item in payload.artifacts]

        def _build_zip() -> tuple[bytes, list[dict[str, str]], list[dict[str, str]]]:
            buffer = io.BytesIO()
            included: list[dict[str, str]] = []
            missing: list[dict[str, str]] = []
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for ref in refs:
                    path = store.get_artifact_path(
                        workspace_dir(),
                        ref["skill"],
                        ref["run_id"],
                        ref["filename"],
                    )
                    if path is None:
                        missing.append(ref)
                        continue
                    archive_name = "/".join(
                        [
                            _zip_segment(ref["skill"], "skill"),
                            _zip_segment(ref["run_id"], "run"),
                            path.name,
                        ]
                    )
                    archive.write(path, archive_name)
                    included.append({**ref, "archive_path": archive_name})
                archive.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "workspace": get_settings().workspace,
                            "included": included,
                            "missing": missing,
                        },
                        indent=2,
                    ),
                )
            return buffer.getvalue(), included, missing

        content, included, missing = await asyncio.to_thread(_build_zip)
        if not included:
            raise HTTPException(404, "No selected artifacts could be found for ZIP download")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"theseus-studio-products-{stamp}.zip"
        return Response(
            content,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Theseus-Zip-Count": str(len(included)),
                "X-Theseus-Zip-Missing": str(len(missing)),
            },
        )

    @app.delete("/api/ui/studio/artifacts", tags=["theseus-ui"])
    async def delete_studio_artifacts_route(
        payload: StudioArtifactDeletePayload = Body(...),
    ) -> JSONResponse:
        store = run_store_factory()
        result = await asyncio.to_thread(
            store.trash_artifacts,
            workspace_dir(),
            [item.model_dump() for item in payload.artifacts],
        )
        return JSONResponse(
            {
                "trashed": result["trashed"],
                "missing": result["missing"],
                "trashed_count": len(result["trashed"]),
                "missing_count": len(result["missing"]),
            }
        )

    @app.post("/api/ui/studio/trash/restore", tags=["theseus-ui"])
    async def restore_studio_artifacts_route(
        payload: StudioTrashRestorePayload = Body(...),
    ) -> JSONResponse:
        store = run_store_factory()
        result = await asyncio.to_thread(
            store.restore_trashed_artifacts,
            workspace_dir(),
            [item.trash_id for item in payload.artifacts],
        )
        return JSONResponse(
            {
                "restored": result["restored"],
                "missing": result["missing"],
                "conflicts": result["conflicts"],
                "restored_count": len(result["restored"]),
                "missing_count": len(result["missing"]),
                "conflict_count": len(result["conflicts"]),
            }
        )

    @app.delete("/api/ui/studio/trash", tags=["theseus-ui"])
    async def empty_studio_trash_route() -> JSONResponse:
        store = run_store_factory()
        result = await asyncio.to_thread(
            store.purge_trashed_artifacts,
            workspace_dir(),
        )
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "purged": result["purged"],
                "skipped": result["skipped"],
            }
        )


__all__ = ["register_studio_ui_routes"]