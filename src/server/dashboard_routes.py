"""Ariadne's Thread dashboard routes (174.4).

Mounts the main Project Theseus app shell at `/` and `/workspace/{name}`.
Ariadne itself lives in `index.html` as the Dashboard view, so `/ui/` keeps the
same URL users already know while the first screen becomes the global command
center.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute

logger = logging.getLogger(__name__)


def _drop_route(app: FastAPI, path: str) -> None:
    """Remove any existing APIRoute matching `path` so we can override it."""
    keep = []
    for route in app.router.routes:
        if isinstance(route, APIRoute) and route.path == path:
            continue
        keep.append(route)
    app.router.routes[:] = keep


def register_dashboard_routes(app: FastAPI, *, static_dir: Path) -> None:
    """Register Ariadne app shell at `/` and `/workspace/{name}`.

    LightRAG ships a `GET /` redirect to `/webui`; we drop it so Theseus opens
    directly to the Ariadne Dashboard view. The `/ui` StaticFiles mount remains
    the canonical app URL and serves `index.html` plus child assets.
    """
    workbench_html = static_dir / "index.html"

    if not workbench_html.exists():
        logger.warning(
            "Project Theseus index.html missing at %s — dashboard routes skipped",
            workbench_html,
        )
        return

    _drop_route(app, "/")

    @app.get("/", include_in_schema=False)
    async def _ariadne_root() -> FileResponse:
        return FileResponse(str(workbench_html))

    @app.get("/workspace/{name}", include_in_schema=False)
    async def _workspace_view(name: str) -> FileResponse:  # noqa: ARG001 — name surfaced by URL
        return FileResponse(str(workbench_html))

    logger.info(
        "✅ Ariadne dashboard app shell mounted at / (canonical app at /ui)"
    )
