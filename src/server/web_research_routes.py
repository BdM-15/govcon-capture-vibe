"""UI routes for per-workspace external web research settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.web_research.config import web_research_settings
from src.web_research.service import provider_status
from src.web_research.settings_store import UI_SETTING_KEYS, WebResearchSettingsStore


class WebResearchSettingsUpdate(BaseModel):
    enabled: bool | None = None
    enable_search: bool | None = None
    enable_fetch: bool | None = None
    enable_firecrawl: bool | None = None
    enable_direct_fetch: bool | None = None
    enable_crawl4ai: bool | None = None
    fetch_timeout_seconds: float | None = Field(None, ge=3.0, le=300.0)
    max_content_chars: int | None = Field(None, ge=500, le=200_000)
    max_search_results: int | None = Field(None, ge=1, le=20)
    cache_ttl_seconds: int | None = Field(None, ge=0, le=2_592_000)


def _settings_payload(
    store: WebResearchSettingsStore,
    *,
    workspace_dir: Path,
    workspace_name: str,
) -> dict[str, Any]:
    settings = store.read()
    effective = web_research_settings(workspace_dir=workspace_dir)
    return {
        "workspace": workspace_name,
        "settings": settings,
        "defaults": store.defaults(),
        "providers": provider_status(effective),
        "storage_path": str(store.path().name),
    }


def register_web_research_settings_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
    workspace_name: Callable[[], str],
) -> None:
    """Register GET/PUT/reset routes for web research UI settings."""

    store = WebResearchSettingsStore(workspace_dir)

    @app.get("/api/ui/settings/web-research", tags=["theseus-ui"])
    async def get_web_research_settings() -> JSONResponse:
        return JSONResponse(
            _settings_payload(
                store,
                workspace_dir=workspace_dir(),
                workspace_name=workspace_name(),
            )
        )

    @app.put("/api/ui/settings/web-research", tags=["theseus-ui"])
    async def update_web_research_settings(
        payload: WebResearchSettingsUpdate,
    ) -> JSONResponse:
        current = store.read()
        updates = payload.model_dump(exclude_none=True)
        for key in UI_SETTING_KEYS:
            if key in updates:
                current[key] = updates[key]
        try:
            store.write(current)
        except OSError as exc:
            raise HTTPException(500, f"Failed writing settings: {exc}") from exc
        return JSONResponse(
            {
                "settings": store.read(),
                "providers": provider_status(
                    web_research_settings(workspace_dir=workspace_dir())
                ),
            }
        )

    @app.post("/api/ui/settings/web-research/reset", tags=["theseus-ui"])
    async def reset_web_research_settings() -> JSONResponse:
        try:
            settings = store.reset()
        except OSError as exc:
            raise HTTPException(500, f"Failed resetting settings: {exc}") from exc
        return JSONResponse(
            {
                "settings": settings,
                "providers": provider_status(
                    web_research_settings(workspace_dir=workspace_dir())
                ),
            }
        )