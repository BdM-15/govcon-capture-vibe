"""Skill invocation routes for Project Theseus UI."""

from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.core import get_settings
from src.skills import get_skill_manager
from src.skills.context import (
    build_skill_briefing_book,
    retrieve_relevant_entities_for_skill,
)
from src.skills.settings import SkillSettingsStore, resolve_skill_runtime_mode

QueryDataFunc = Callable[[str, str, list[dict], dict], Awaitable[dict]]
LlmFunc = Callable[[str], Awaitable[str]]
SliceFunc = Callable[[Path, Optional[list[str]], int, int, int, Optional[set[str]]], dict[str, Any]]
RetrieveFunc = Callable[[Optional[QueryDataFunc], str, str, str, int], Awaitable[dict[str, Any]]]


def register_skill_invoke_ui_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
    settings_store: SkillSettingsStore,
    data_func: Optional[QueryDataFunc],
    llm_func: Optional[LlmFunc],
    workspace_name: Callable[[], str] | None = None,
    manager_factory: Callable[[], Any] = get_skill_manager,
    slice_workspace_entities: SliceFunc = build_skill_briefing_book,
    retrieve_entities_for_skill: RetrieveFunc = retrieve_relevant_entities_for_skill,
) -> None:
    """Register POST /api/ui/skills/{name}/invoke."""
    if workspace_name is None:
        workspace_name = lambda: get_settings().workspace

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
        return slice_workspace_entities(
            workspace_dir(),
            entity_types,
            max_per_type,
            max_chunks_per_entity,
            max_relationships_per_entity,
            relevant_entity_names,
        )

    async def _retrieve_relevant_entities_for_skill(
        prompt: str,
        skill_description: str,
        mode: str,
        top_k: int,
    ) -> dict[str, Any]:
        return await retrieve_entities_for_skill(
            data_func,
            prompt,
            skill_description,
            mode,
            top_k,
        )

    @app.post("/api/ui/skills/{name}/invoke", tags=["theseus-ui"])
    async def invoke_skill_route(
        name: str,
        payload: SkillInvokePayload = Body(...),
    ) -> JSONResponse:
        if llm_func is None:
            raise HTTPException(
                503,
                "Skill invocation requires an llm_func; server was started without one",
            )
        mgr = manager_factory()
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
                    workspace=workspace_name(),
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
                workspace=workspace_name(),
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