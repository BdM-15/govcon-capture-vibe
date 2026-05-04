"""Agent-skill UI routes for Project Theseus."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.core import get_settings
from src.server.skill_run_ui_routes import register_skill_run_ui_routes
from src.server.skill_settings_ui_routes import register_skill_settings_ui_routes
from src.skills import get_skill_manager
from src.skills.context import (
    build_skill_briefing_book,
    retrieve_relevant_entities_for_skill,
)
from src.skills.settings import (
    SkillSettingsStore,
    resolve_skill_runtime_mode,
)

QueryDataFunc = Callable[
    [str, str, list[dict], dict],
    Awaitable[dict],
]
LlmFunc = Callable[[str], Awaitable[str]]

class SkillInstallPayload(BaseModel):
    """Body for POST /api/ui/skills/install."""

    url: str = Field(..., description="https://github.com/<org>/<repo> URL")
    name: Optional[str] = Field(None, description="Override target skill slug")


def register_skill_ui_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
    data_func: Optional[QueryDataFunc],
    llm_func: Optional[LlmFunc],
) -> None:
    """Register skill, run, Studio, and chunk-preview UI endpoints."""

    settings_store = SkillSettingsStore(workspace_dir)

    def _default_max_entities_per_type() -> int:
        return int(settings_store.read()["max_entities_per_type"])

    def _default_max_chunks_per_entity() -> int:
        return int(settings_store.read()["max_chunks_per_entity"])

    def _default_max_relationships_per_entity() -> int:
        return int(settings_store.read()["max_relationships_per_entity"])

    def _default_skill_retrieval_mode() -> str:
        return str(settings_store.read()["retrieval_mode"])

    def _default_skill_retrieval_top_k() -> int:
        return int(settings_store.read()["retrieval_top_k"])

    class SkillInvokePayload(BaseModel):
        """Body for POST /api/ui/skills/{name}/invoke."""

        prompt: str = Field("", description="Free-text user instruction; may be empty")
        entity_types: Optional[list[str]] = Field(
            None,
            description=(
                "Restrict the workspace context payload to these entity_types. "
                "Defaults to the skill's recommended slice (see SKILL.md)."
            ),
        )
        max_entities_per_type: int = Field(
            default_factory=_default_max_entities_per_type,
            ge=1,
            le=500,
        )
        max_chunks_per_entity: int = Field(
            default_factory=_default_max_chunks_per_entity,
            ge=0,
            le=10,
            description=(
                "Verbatim source-chunk count attached per entity. "
                "0 disables the chunks block."
            ),
        )
        max_relationships_per_entity: int = Field(
            default_factory=_default_max_relationships_per_entity,
            ge=0,
            le=50,
            description=(
                "KG edges attached per entity. "
                "0 disables the relationships block."
            ),
        )
        retrieval_mode: str = Field(
            default_factory=_default_skill_retrieval_mode,
            description="Skill retrieval mode: hybrid|local|global|naive|mix|off.",
        )
        retrieval_top_k: int = Field(
            default_factory=_default_skill_retrieval_top_k,
            ge=5,
            le=500,
            description="Cap on retrieval-ranked entities promoted into the briefing book.",
        )

    def _slice_workspace_entities(
        entity_types: Optional[list[str]],
        max_per_type: int,
        max_chunks_per_entity: int = 2,
        max_relationships_per_entity: int = 5,
        relevant_entity_names: Optional[set[str]] = None,
    ) -> dict[str, Any]:
        return build_skill_briefing_book(
            workspace_dir(),
            entity_types,
            max_per_type,
            max_chunks_per_entity=max_chunks_per_entity,
            max_relationships_per_entity=max_relationships_per_entity,
            relevant_entity_names=relevant_entity_names,
        )

    async def _retrieve_relevant_entities_for_skill(
        prompt: str,
        skill_description: str,
        mode: str,
        top_k: int,
    ) -> dict[str, Any]:
        return await retrieve_relevant_entities_for_skill(
            data_func,
            prompt,
            skill_description,
            mode,
            top_k,
        )

    register_skill_settings_ui_routes(
        app,
        settings_store=settings_store,
        workspace_name=lambda: get_settings().workspace,
    )

    @app.get("/api/ui/skills", tags=["theseus-ui"])
    async def list_skills_route() -> JSONResponse:
        mgr = get_skill_manager()
        return JSONResponse({"skills": mgr.list_skills()})

    @app.post("/api/ui/skills/refresh", tags=["theseus-ui"])
    async def refresh_skills_route() -> JSONResponse:
        mgr = get_skill_manager()
        mgr.discover()
        return JSONResponse({"skills": mgr.list_skills()})

    @app.get("/api/ui/skills/{name}", tags=["theseus-ui"])
    async def get_skill_route(name: str) -> JSONResponse:
        mgr = get_skill_manager()
        detail = mgr.get_skill_detail(name)
        if detail is None:
            raise HTTPException(404, f"Unknown skill: {name}")
        return JSONResponse(detail)

    @app.post("/api/ui/skills/install", tags=["theseus-ui"])
    async def install_skill_route(payload: SkillInstallPayload) -> JSONResponse:
        mgr = get_skill_manager()
        try:
            skill = await mgr.install_from_github(payload.url, name=payload.name)
        except FileExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return JSONResponse({"skill": skill.to_summary()})

    @app.delete("/api/ui/skills/{name}", tags=["theseus-ui"])
    async def uninstall_skill_route(name: str) -> JSONResponse:
        mgr = get_skill_manager()
        try:
            removed = await mgr.uninstall(name)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        if not removed:
            raise HTTPException(404, f"Unknown skill: {name}")
        return JSONResponse({"removed": name})

    @app.post("/api/ui/skills/{name}/invoke", tags=["theseus-ui"])
    async def invoke_skill_route(
        name: str,
        payload: SkillInvokePayload,
    ) -> JSONResponse:
        if llm_func is None:
            raise HTTPException(
                503,
                "Skill invocation requires an llm_func; server was started without one",
            )
        mgr = get_skill_manager()
        skill = mgr.get_skill(name)
        skill_desc = skill.frontmatter.description if skill is not None else ""
        frontmatter_mode = (
            skill.frontmatter.runtime_mode if skill is not None else "legacy"
        )
        effective_mode = resolve_skill_runtime_mode(frontmatter_mode)

        if effective_mode == "tools":
            try:
                result = await mgr.invoke(
                    name,
                    workspace=get_settings().workspace,
                    user_prompt=payload.prompt,
                    entity_payload={},
                    llm=llm_func,
                    workspace_root=workspace_dir(),
                    slice_fn=_slice_workspace_entities,
                    retrieve_fn=_retrieve_relevant_entities_for_skill,
                )
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            return JSONResponse(
                {
                    "skill": result.skill,
                    "workspace": result.workspace,
                    "response": result.response,
                    "entities_used": result.entities_used,
                    "warnings": result.warnings,
                    "elapsed_ms": result.elapsed_ms,
                    "prompt_tokens_estimate": result.prompt_tokens_estimate,
                    "run_id": result.run_id,
                    "run_dir": result.run_dir,
                    "runtime_mode": "tools",
                    "retrieval": {
                        "mode": "tools",
                        "used": True,
                        "reason": "tools-mode runtime",
                    },
                }
            )

        retrieval = await _retrieve_relevant_entities_for_skill(
            prompt=payload.prompt,
            skill_description=skill_desc,
            mode=payload.retrieval_mode,
            top_k=payload.retrieval_top_k,
        )
        whitelist = retrieval["names"] or None
        context = _slice_workspace_entities(
            payload.entity_types,
            payload.max_entities_per_type,
            max_chunks_per_entity=payload.max_chunks_per_entity,
            max_relationships_per_entity=payload.max_relationships_per_entity,
            relevant_entity_names=whitelist,
        )
        context["retrieval_metadata"] = retrieval["metadata"]
        try:
            result = await mgr.invoke(
                name,
                workspace=get_settings().workspace,
                user_prompt=payload.prompt,
                entity_payload=context,
                llm=llm_func,
                workspace_root=workspace_dir(),
            )
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return JSONResponse(
            {
                "skill": result.skill,
                "workspace": result.workspace,
                "response": result.response,
                "entities_used": result.entities_used,
                "warnings": result.warnings,
                "elapsed_ms": result.elapsed_ms,
                "prompt_tokens_estimate": result.prompt_tokens_estimate,
                "run_id": result.run_id,
                "run_dir": result.run_dir,
                "runtime_mode": "legacy",
                "retrieval": retrieval["metadata"],
            }
        )

    register_skill_run_ui_routes(app, workspace_dir=workspace_dir)
