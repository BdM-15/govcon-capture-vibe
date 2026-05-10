"""Global markdown-store routes for Ariadne's Thread."""

from __future__ import annotations

from datetime import date
import re
import unicodedata
from collections.abc import Awaitable
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.core.global_store import GlobalStore

_GLOBAL_BUCKETS = ("inbox", "notes", "llm-wiki", "intel")
_BUCKET_SET = frozenset(_GLOBAL_BUCKETS)
PromotionRefreshFunc = Callable[..., Awaitable[dict[str, Any]]]


class GlobalCapturePayload(BaseModel):
    """Body for POST /api/global/capture."""

    content: str = Field(..., min_length=1)
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    bucket: str = Field(default="inbox", min_length=1, max_length=32)
    source: str = Field(default="capture", min_length=1, max_length=32)
    status: str | None = Field(default=None, min_length=1, max_length=32)
    tags: list[str] = Field(default_factory=list, min_length=1, max_length=8)
    workspace: str | None = Field(default=None, min_length=1, max_length=64)
    wikilinks: list[str] = Field(default_factory=list, max_length=16)
    priority: str | None = Field(default=None, min_length=1, max_length=16)


class GlobalPromotePayload(BaseModel):
    """Body for POST /api/global/promote."""

    path: str = Field(..., min_length=1, max_length=255)
    workspace: str = Field(..., min_length=1, max_length=64)


class GlobalUnpromotePayload(GlobalPromotePayload):
    """Body for DELETE /api/global/promote."""

    delete_target: bool = True


class GlobalRefreshPayload(GlobalPromotePayload):
    """Body for POST /api/global/promote/refresh."""

    delete_existing: bool = True
    delete_llm_cache: bool = False


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:80] or "capture"


def _ensure_bucket(bucket: str) -> str:
    cleaned = (bucket or "").strip()
    if cleaned not in _BUCKET_SET:
        raise HTTPException(400, f"Unsupported global bucket: {bucket}")
    return cleaned


def _frontmatter_text(payload: GlobalCapturePayload, *, today: str, bucket: str) -> str:
    lines = [
        "---",
        f"date: {today}",
        f"source: {payload.source}",
        f"status: {payload.status or ('inbox' if bucket == 'inbox' else 'evergreen')}",
        f"tags: [{', '.join(payload.tags)}]",
    ]
    if payload.workspace:
        lines.append(f"workspace: {payload.workspace}")
    if payload.wikilinks:
        lines.append(f"wikilinks: {' '.join(payload.wikilinks)}")
    if payload.priority:
        lines.append(f"priority: {payload.priority}")
    lines.extend(["---", "", payload.content.strip(), ""])
    return "\n".join(lines)


def register_global_routes(
    app: FastAPI,
    *,
    store_factory: Callable[[], GlobalStore] | None = None,
    workspace_root: Callable[[], Path] | None = None,
    today: Callable[[], str] | None = None,
    promotion_refresh_func: PromotionRefreshFunc | None = None,
) -> None:
    """Register `/api/global/*` routes backed by `GlobalStore`."""
    if store_factory is None:
        store_factory = GlobalStore
    if workspace_root is None:
        workspace_root = lambda: (Path(__file__).resolve().parents[2] / "rag_storage").resolve()
    if today is None:
        today = lambda: date.today().isoformat()

    def _list_bucket(bucket: str, limit: int) -> JSONResponse:
        store = store_factory()
        entries = store.list(bucket)[:limit]
        return JSONResponse({"bucket": bucket, "entries": entries})

    @app.get("/api/global/inbox", tags=["theseus-ui"])
    async def get_global_inbox(limit: int = Query(default=20, ge=1, le=200)) -> JSONResponse:
        return _list_bucket("inbox", limit)

    @app.get("/api/global/notes", tags=["theseus-ui"])
    async def get_global_notes(limit: int = Query(default=20, ge=1, le=200)) -> JSONResponse:
        return _list_bucket("notes", limit)

    @app.get("/api/global/llm-wiki", tags=["theseus-ui"])
    async def get_global_llm_wiki(limit: int = Query(default=20, ge=1, le=200)) -> JSONResponse:
        return _list_bucket("llm-wiki", limit)

    @app.get("/api/global/intel", tags=["theseus-ui"])
    async def get_global_intel(limit: int = Query(default=20, ge=1, le=200)) -> JSONResponse:
        return _list_bucket("intel", limit)

    @app.post("/api/global/capture", tags=["theseus-ui"])
    async def capture_global_note(payload: GlobalCapturePayload) -> JSONResponse:
        bucket = _ensure_bucket(payload.bucket)
        slug = _slugify(payload.slug or payload.content.splitlines()[0])
        current_day = today()
        relative_path = f"{bucket}/{current_day}-{slug}.md"
        content = _frontmatter_text(payload, today=current_day, bucket=bucket)
        store = store_factory()
        try:
            store.write(relative_path, content)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        entry = store.list(relative_path)
        return JSONResponse({"path": relative_path, "entry": entry[0] if entry else None})

    @app.post("/api/global/promote", tags=["theseus-ui"])
    async def promote_global_note(payload: GlobalPromotePayload) -> JSONResponse:
        store = store_factory()
        try:
            result = store.promote(
                payload.path,
                workspace=payload.workspace,
                workspace_root=workspace_root(),
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return JSONResponse(result)

    @app.get("/api/global/promotions", tags=["theseus-ui"])
    async def list_global_promotions(
        workspace: str = Query(..., min_length=1, max_length=64),
        active_only: bool = False,
    ) -> JSONResponse:
        store = store_factory()
        try:
            promotions = store.list_promotions(
                workspace=workspace,
                workspace_root=workspace_root(),
                active_only=active_only,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return JSONResponse({"workspace": workspace, "promotions": promotions})

    @app.delete("/api/global/promote", tags=["theseus-ui"])
    async def unpromote_global_note(payload: GlobalUnpromotePayload) -> JSONResponse:
        store = store_factory()
        try:
            result = store.unpromote(
                payload.path,
                workspace=payload.workspace,
                workspace_root=workspace_root(),
                delete_target=payload.delete_target,
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return JSONResponse(result)

    if promotion_refresh_func is not None:

        @app.post("/api/global/promote/refresh", tags=["theseus-ui"])
        async def refresh_global_promotion(payload: GlobalRefreshPayload) -> JSONResponse:
            try:
                result = await promotion_refresh_func(
                    path=payload.path,
                    workspace=payload.workspace,
                    delete_existing=payload.delete_existing,
                    delete_llm_cache=payload.delete_llm_cache,
                )
            except FileNotFoundError as exc:
                raise HTTPException(404, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return JSONResponse(result)


__all__ = ["register_global_routes"]