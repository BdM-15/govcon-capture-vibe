"""Ariadne's Thread dashboard routes (174.4).

Mounts the new top-level dashboard UI at `/` and re-routes the legacy
single-workspace Capture Workbench to `/workspace/{name}`.

The dashboard is a thin Alpine page (`dashboard.html`) that wires into the
174.3 `/api/global/*` endpoints plus the existing `/workspaces` rollup.
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
    """Register Ariadne dashboard at `/` and Workbench at `/workspace/{name}`.

    LightRAG ships a `GET /` redirect to `/webui`; we drop it so Ariadne
    becomes the actual landing page. The legacy SPA at `/ui/index.html`
    stays mounted unchanged — `/workspace/{name}` is just a friendlier alias
    that surfaces the workspace name in the URL for bookmarking.
    """
    dashboard_html = static_dir / "dashboard.html"
    workbench_html = static_dir / "index.html"

    if not dashboard_html.exists():
        logger.warning(
            "Ariadne dashboard.html missing at %s — dashboard routes skipped",
            dashboard_html,
        )
        return

    _drop_route(app, "/")
    _drop_route(app, "/ui")
    _drop_route(app, "/ui/")

    @app.get("/", include_in_schema=False)
    async def _ariadne_root() -> FileResponse:
        return FileResponse(str(dashboard_html))

    # `/ui` and `/ui/` were the legacy Capture Workbench mount; they now serve
    # the Ariadne dashboard so existing bookmarks land on the new command center.
    # The static mount at `/ui` still serves child assets (styles, js, images).
    @app.get("/ui", include_in_schema=False)
    async def _ariadne_ui() -> FileResponse:
        return FileResponse(str(dashboard_html))

    @app.get("/ui/", include_in_schema=False)
    async def _ariadne_ui_slash() -> FileResponse:
        return FileResponse(str(dashboard_html))

    @app.get("/workspace/{name}", include_in_schema=False)
    async def _workspace_view(name: str) -> FileResponse:  # noqa: ARG001 — name surfaced by URL
        return FileResponse(str(workbench_html))

    logger.info(
        "✅ Ariadne dashboard mounted at / and /ui (workbench at /workspace/{name})"
    )
