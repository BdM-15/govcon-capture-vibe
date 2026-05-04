"""Skill catalog CRUD routes for Project Theseus UI."""

from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.skills import get_skill_manager


class SkillInstallPayload(BaseModel):
    """Body for POST /api/ui/skills/install."""

    url: str = Field(..., description="https://github.com/<org>/<repo> URL")
    name: Optional[str] = Field(None, description="Override target skill slug")


def register_skill_catalog_ui_routes(
    app: FastAPI,
    *,
    manager_factory: Callable[[], Any] = get_skill_manager,
) -> None:
    """Register skill catalog list/detail/install/uninstall routes."""

    @app.get("/api/ui/skills", tags=["theseus-ui"])
    async def list_skills_route() -> JSONResponse:
        mgr = manager_factory()
        return JSONResponse({"skills": mgr.list_skills()})

    @app.post("/api/ui/skills/refresh", tags=["theseus-ui"])
    async def refresh_skills_route() -> JSONResponse:
        mgr = manager_factory()
        mgr.discover()
        return JSONResponse({"skills": mgr.list_skills()})

    @app.get("/api/ui/skills/{name}", tags=["theseus-ui"])
    async def get_skill_route(name: str) -> JSONResponse:
        mgr = manager_factory()
        detail = mgr.get_skill_detail(name)
        if detail is None:
            raise HTTPException(404, f"Unknown skill: {name}")
        return JSONResponse(detail)

    @app.post("/api/ui/skills/install", tags=["theseus-ui"])
    async def install_skill_route(payload: SkillInstallPayload) -> JSONResponse:
        mgr = manager_factory()
        try:
            skill = await mgr.install_from_github(payload.url, name=payload.name)
        except FileExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return JSONResponse({"skill": skill.to_summary()})

    @app.delete("/api/ui/skills/{name}", tags=["theseus-ui"])
    async def uninstall_skill_route(name: str) -> JSONResponse:
        mgr = manager_factory()
        try:
            removed = await mgr.uninstall(name)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        if not removed:
            raise HTTPException(404, f"Unknown skill: {name}")
        return JSONResponse({"removed": name})