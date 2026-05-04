"""Skill settings routes for Project Theseus UI."""

from __future__ import annotations

from typing import Callable, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.core import get_settings
from src.skills.settings import SkillSettingsStore, VALID_SKILL_RETRIEVAL_MODES


class SkillSettingsUpdate(BaseModel):
    """Per-workspace skill briefing-book and retrieval overrides."""

    max_entities_per_type: Optional[int] = Field(default=None, ge=1, le=500)
    max_chunks_per_entity: Optional[int] = Field(default=None, ge=0, le=10)
    max_relationships_per_entity: Optional[int] = Field(default=None, ge=0, le=50)
    retrieval_mode: Optional[str] = Field(default=None, max_length=20)
    retrieval_top_k: Optional[int] = Field(default=None, ge=5, le=500)


def register_skill_settings_ui_routes(
    app: FastAPI,
    *,
    settings_store: SkillSettingsStore,
    workspace_name: Callable[[], str] | None = None,
) -> None:
    """Register skill settings read/update/reset routes."""
    if workspace_name is None:
        workspace_name = lambda: get_settings().workspace

    @app.get("/api/ui/settings/skills", tags=["theseus-ui"])
    async def get_skill_settings() -> JSONResponse:
        return JSONResponse(
            {
                "workspace": workspace_name(),
                "settings": settings_store.read(),
                "defaults": settings_store.defaults(),
            }
        )

    @app.put("/api/ui/settings/skills", tags=["theseus-ui"])
    async def update_skill_settings(payload: SkillSettingsUpdate) -> JSONResponse:
        current = settings_store.read()
        updates = payload.model_dump(exclude_none=True)
        if "retrieval_mode" in updates:
            mode = (updates["retrieval_mode"] or "").strip().lower()
            if mode not in VALID_SKILL_RETRIEVAL_MODES:
                raise HTTPException(400, f"Unsupported retrieval_mode: {mode}")
            updates["retrieval_mode"] = mode
        current.update(updates)
        try:
            settings_store.write(current)
        except OSError as exc:
            raise HTTPException(500, f"Failed writing settings: {exc}") from exc
        return JSONResponse({"settings": current})

    @app.post("/api/ui/settings/skills/reset", tags=["theseus-ui"])
    async def reset_skill_settings() -> JSONResponse:
        path = settings_store.path()
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            raise HTTPException(500, f"Failed resetting settings: {exc}") from exc
        return JSONResponse({"settings": settings_store.defaults()})