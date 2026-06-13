"""Agent-skill UI routes for Project Theseus."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from src.core import get_settings
from src.server.chunk_store import get_text_chunk
from src.skills import get_skill_manager
from src.skills.chain_models import ChainRunState, ChainSpec, ChainStepSpec
from src.skills.mission_readiness_chain import build_mission_readiness_chain_spec
from src.skills.context_artifacts import (
    ContextArtifactRef,
    format_context_artifacts_prompt_block,
    resolve_context_artifacts,
    to_input_artifacts_payload,
)
from src.skills.context import (
    build_skill_briefing_book,
    retrieve_relevant_entities_for_skill,
)
from src.skills.skill_emitters import auto_emit_artifacts
from src.skills.runs import resolve_artifact_mime
from src.server.skill_invoke_support import (
    build_briefing_context,
    make_retrieve_fn,
    make_slice_fn,
    resolve_plan_from_store,
    skill_skips_coverage_boost,
)
from src.skills.retrieval_plan import retrieval_metadata_from_plan
from src.skills.settings import (
    VALID_SKILL_RETRIEVAL_MODES,
    resolve_skill_runtime_mode,
    skill_tools_runtime_defaults,
    skill_tools_runtime_settings,
    SKILL_TOOLS_RUNTIME_ENV_KEYS,
)

logger = logging.getLogger(__name__)

QueryDataFunc = Callable[[str, str, list[dict], dict], Awaitable[dict]]
LlmFunc = Callable[[str], Awaitable[str]]
SliceFunc = Callable[
    [Path, Optional[list[str]], int, int, int, Optional[set[str]]],
    dict[str, Any],
]
RetrieveFunc = Callable[
    [Optional[QueryDataFunc], str, str, str, dict[str, Any]],
    Awaitable[dict[str, Any]],
]

_SKILL_TO_QUERY_KEYS = {
    "retrieval_mode": "mode",
    "retrieval_top_k": "top_k",
    "max_entities_per_type": "skill_max_entities_per_type",
    "max_chunks_per_entity": "skill_max_chunks_per_entity",
    "max_relationships_per_entity": "skill_max_relationships_per_entity",
}


def _skill_settings_projection(query_settings: dict[str, Any]) -> dict[str, Any]:
    """Expose query settings through the legacy skill-settings API shape."""
    return {
        "retrieval_mode": query_settings.get("mode", "mix"),
        "retrieval_top_k": query_settings.get("top_k", 40),
        "max_entities_per_type": query_settings.get("skill_max_entities_per_type", 80),
        "max_chunks_per_entity": query_settings.get("skill_max_chunks_per_entity", 10),
        "max_relationships_per_entity": query_settings.get(
            "skill_max_relationships_per_entity", 25
        ),
    }


def _skill_settings_defaults(query_defaults: dict[str, Any]) -> dict[str, Any]:
    return _skill_settings_projection(query_defaults)


class SkillInstallPayload(BaseModel):
    """Body for POST /api/ui/skills/install."""

    url: str = Field(..., description="https://github.com/<org>/<repo> URL")
    name: Optional[str] = Field(None, description="Override target skill slug")


class SkillSettingsUpdate(BaseModel):
    """Per-workspace skill briefing-book and retrieval overrides."""

    max_entities_per_type: Optional[int] = Field(default=None, ge=1, le=500)
    max_chunks_per_entity: Optional[int] = Field(default=None, ge=0, le=10)
    max_relationships_per_entity: Optional[int] = Field(default=None, ge=0, le=50)
    retrieval_mode: Optional[str] = Field(default=None, max_length=20)
    retrieval_top_k: Optional[int] = Field(default=None, ge=5, le=500)


class SkillRuntimeSettingsUpdate(BaseModel):
    """Global tools-mode runtime ceilings persisted into `.env`."""

    max_turns: Optional[int] = Field(default=None, ge=1, le=500)
    llm_timeout_seconds: Optional[float] = Field(default=None, ge=1, le=3600)
    mcp_handshake_timeout: Optional[float] = Field(default=None, ge=0.1, le=3600)
    mcp_tool_call_timeout: Optional[float] = Field(default=None, ge=0.1, le=3600)
    mcp_shutdown_timeout: Optional[float] = Field(default=None, ge=0.1, le=3600)
    max_tool_result_chars: Optional[int] = Field(default=None, ge=500, le=2_000_000)
    max_read_bytes: Optional[int] = Field(default=None, ge=1_000, le=5_000_000)
    max_write_bytes: Optional[int] = Field(default=None, ge=1_000, le=20_000_000)
    max_script_seconds: Optional[int] = Field(default=None, ge=1, le=86_400)
    max_kg_entities_per_type: Optional[int] = Field(default=None, ge=1, le=5_000)
    max_kg_chunks: Optional[int] = Field(default=None, ge=1, le=5_000)
    max_kg_chunks_per_entity: Optional[int] = Field(default=None, ge=0, le=500)
    max_kg_relationships_per_entity: Optional[int] = Field(default=None, ge=0, le=500)


def _run_dir_for_skill_run(workspace_root: Path, skill_name: str, run_id: str) -> Path | None:
    base = (Path(workspace_root) / "skill_runs" / skill_name).resolve()
    run_dir = (base / run_id).resolve()
    try:
        run_dir.relative_to(base)
    except ValueError:
        return None
    if not run_dir.is_dir():
        return None
    return run_dir


def _skill_response_payload(
    result: Any,
    *,
    runtime_mode: str,
    retrieval: dict[str, Any],
) -> dict[str, Any]:
    return {
        "skill": result.skill,
        "workspace": result.workspace,
        "response": result.response,
        "entities_used": result.entities_used,
        "warnings": result.warnings,
        "elapsed_ms": result.elapsed_ms,
        "prompt_tokens_estimate": result.prompt_tokens_estimate,
        "run_id": result.run_id,
        "run_dir": result.run_dir,
        "finish_reason": getattr(result, "finish_reason", ""),
        "runtime_mode": runtime_mode,
        "retrieval": retrieval,
    }


def _project_chain_payload(mgr: Any, payload: dict[str, Any]) -> dict[str, Any]:
    projector = getattr(mgr, "project_chain_run", None)
    if callable(projector):
        return projector(payload)
    return payload


def _project_skill_run_payload(mgr: Any, payload: dict[str, Any]) -> dict[str, Any]:
    projector = getattr(mgr, "project_run", None)
    if callable(projector):
        return projector(payload)
    return payload


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


def register_skill_settings_ui_routes(
    app: FastAPI,
    *,
    query_settings_store: Any,
    workspace_name: Callable[[], str] | None = None,
    set_env_var: Callable[[str, str], None] | None = None,
) -> None:
    """Register skill settings routes backed by Query Tuning (legacy API shape)."""
    if workspace_name is None:
        workspace_name = lambda: get_settings().workspace

    @app.get("/api/ui/settings/skills", tags=["theseus-ui"])
    async def get_skill_settings() -> JSONResponse:
        current = query_settings_store.read()
        return JSONResponse(
            {
                "workspace": workspace_name(),
                "settings": _skill_settings_projection(current),
                "defaults": _skill_settings_defaults(query_settings_store.defaults()),
                "deprecated": True,
                "canonical_endpoint": "/api/ui/settings/query",
                "message": "Skill retrieval is configured in Query Tuning.",
            }
        )

    @app.put("/api/ui/settings/skills", tags=["theseus-ui"])
    async def update_skill_settings(payload: SkillSettingsUpdate) -> JSONResponse:
        current = query_settings_store.read()
        updates = payload.model_dump(exclude_none=True)
        if "retrieval_mode" in updates:
            mode = (updates["retrieval_mode"] or "").strip().lower()
            if mode == "off":
                mode = "bypass"
            elif mode not in VALID_SKILL_RETRIEVAL_MODES and mode != "bypass":
                raise HTTPException(400, f"Unsupported retrieval_mode: {mode}")
            current["mode"] = mode
        for skill_key, query_key in _SKILL_TO_QUERY_KEYS.items():
            if skill_key in updates and skill_key != "retrieval_mode":
                current[query_key] = updates[skill_key]
        try:
            query_settings_store.write(current)
        except OSError as exc:
            raise HTTPException(500, f"Failed writing settings: {exc}") from exc
        return JSONResponse(
            {
                "settings": _skill_settings_projection(current),
                "canonical_endpoint": "/api/ui/settings/query",
            }
        )

    @app.post("/api/ui/settings/skills/reset", tags=["theseus-ui"])
    async def reset_skill_settings() -> JSONResponse:
        try:
            query_settings_store.reset()
        except OSError as exc:
            raise HTTPException(500, f"Failed resetting settings: {exc}") from exc
        return JSONResponse(
            {
                "settings": _skill_settings_defaults(query_settings_store.defaults()),
                "canonical_endpoint": "/api/ui/settings/query",
            }
        )

    @app.get("/api/ui/settings/skills/runtime", tags=["theseus-ui"])
    async def get_skill_runtime_settings() -> JSONResponse:
        return JSONResponse(
            {
                "workspace": workspace_name(),
                "settings": skill_tools_runtime_settings(),
                "defaults": skill_tools_runtime_defaults(),
            }
        )

    @app.put("/api/ui/settings/skills/runtime", tags=["theseus-ui"])
    async def update_skill_runtime_settings(
        payload: SkillRuntimeSettingsUpdate,
    ) -> JSONResponse:
        if set_env_var is None:
            raise HTTPException(503, "Global skill runtime settings are unavailable")
        updates = payload.model_dump(exclude_none=True)
        for key, value in updates.items():
            env_key = SKILL_TOOLS_RUNTIME_ENV_KEYS[key]
            try:
                set_env_var(env_key, str(value))
            except Exception as exc:
                raise HTTPException(500, f"Failed updating {env_key}: {exc}") from exc
        return JSONResponse({"settings": skill_tools_runtime_settings()})

    @app.post("/api/ui/settings/skills/runtime/reset", tags=["theseus-ui"])
    async def reset_skill_runtime_settings() -> JSONResponse:
        if set_env_var is None:
            raise HTTPException(503, "Global skill runtime settings are unavailable")
        defaults = skill_tools_runtime_defaults()
        for key, value in defaults.items():
            env_key = SKILL_TOOLS_RUNTIME_ENV_KEYS[key]
            try:
                set_env_var(env_key, str(value))
            except Exception as exc:
                raise HTTPException(500, f"Failed resetting {env_key}: {exc}") from exc
        return JSONResponse({"settings": skill_tools_runtime_settings()})


def register_skill_invoke_ui_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
    query_settings_store: Any,
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
        max_entities_per_type: Optional[int] = Field(
            None,
            ge=1,
            le=500,
            description="Optional per-request override; defaults to Query Tuning.",
        )
        max_chunks_per_entity: Optional[int] = Field(
            None,
            ge=0,
            le=50,
            description="Optional per-request override; defaults to Query Tuning.",
        )
        max_relationships_per_entity: Optional[int] = Field(
            None,
            ge=0,
            le=50,
            description="Optional per-request override; defaults to Query Tuning.",
        )
        retrieval_mode: Optional[str] = Field(
            None,
            description="Optional per-request override; defaults to Query Tuning mode.",
        )
        retrieval_top_k: Optional[int] = Field(
            None,
            ge=5,
            le=500,
            description="Optional per-request override; defaults to Query Tuning top_k.",
        )
        user_addendum: str = Field(
            "",
            max_length=8000,
            description=(
                "Optional first-run context from Intel Briefings or Agent Skills "
                "(URLs, partner notes, incumbent hints). Appended to prompt."
            ),
        )
        context_artifacts: list[ContextArtifactRef] = Field(
            default_factory=list,
            max_length=5,
            description=(
                "Optional Studio deliverables to attach as context (skill, run_id, filename)."
            ),
        )

    class SkillChainInvokePayload(BaseModel):
        """Body for POST /api/ui/skill-chains/invoke."""

        name: str = Field("skill-chain", min_length=1, max_length=128)
        prompt: str = ""
        preset: str = Field(
            "",
            max_length=64,
            description="Optional built-in chain preset (e.g. mission-readiness).",
        )
        user_addendum: str = Field(
            "",
            max_length=8000,
            description="Optional Intel context appended to the chain prompt.",
        )
        steps: list[ChainStepSpec] = Field(default_factory=list, max_length=20)
        stop_on_error: bool = True
        max_entities_per_type: Optional[int] = Field(None, ge=1, le=500)
        max_chunks_per_entity: Optional[int] = Field(None, ge=0, le=50)
        max_relationships_per_entity: Optional[int] = Field(None, ge=0, le=50)
        retrieval_mode: Optional[str] = None
        retrieval_top_k: Optional[int] = Field(None, ge=5, le=500)

        def resolved_spec(self) -> ChainSpec:
            preset = str(self.preset or "").strip().lower()
            if preset == "mission-readiness":
                return build_mission_readiness_chain_spec(
                    self.prompt,
                    user_addendum=self.user_addendum,
                )
            if preset:
                raise ValueError(f"Unknown chain preset: {preset}")
            if not self.steps:
                raise ValueError("steps required when preset is omitted")
            return ChainSpec(
                name=self.name,
                prompt=self.prompt,
                steps=self.steps,
                stop_on_error=self.stop_on_error,
            )

    class SkillRunRepeatPayload(BaseModel):
        """Body for POST /api/ui/skills/{name}/runs/{run_id}/resume."""

        user_addendum: str = Field("", max_length=8000)
        context_artifacts: list[ContextArtifactRef] = Field(
            default_factory=list,
            max_length=5,
        )
        answers: dict[str, Any] = Field(default_factory=dict)
        entity_types: Optional[list[str]] = Field(None)
        max_entities_per_type: Optional[int] = Field(None, ge=1, le=500)
        max_chunks_per_entity: Optional[int] = Field(None, ge=0, le=50)
        max_relationships_per_entity: Optional[int] = Field(None, ge=0, le=50)
        retrieval_mode: Optional[str] = None
        retrieval_top_k: Optional[int] = Field(None, ge=5, le=500)

    class SkillChainPlanPayload(BaseModel):
        """Body for dynamic chain plan/run routes."""

        prompt: str = Field(..., min_length=1, max_length=4000)
        outcome: str = Field("", max_length=2000)
        max_steps: int = Field(8, ge=1, le=20)
        include_rendering: bool = True
        max_entities_per_type: Optional[int] = Field(None, ge=1, le=500)
        max_chunks_per_entity: Optional[int] = Field(None, ge=0, le=50)
        max_relationships_per_entity: Optional[int] = Field(None, ge=0, le=50)
        retrieval_mode: Optional[str] = None
        retrieval_top_k: Optional[int] = Field(None, ge=5, le=500)

    class SkillChainRepeatPayload(BaseModel):
        """Body for chain rerun/resume routes."""

        from_step_id: str = Field("", max_length=64)
        user_addendum: str = Field("", max_length=8000)
        max_entities_per_type: Optional[int] = Field(None, ge=1, le=500)
        max_chunks_per_entity: Optional[int] = Field(None, ge=0, le=50)
        max_relationships_per_entity: Optional[int] = Field(None, ge=0, le=50)
        retrieval_mode: Optional[str] = None
        retrieval_top_k: Optional[int] = Field(None, ge=5, le=500)

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

    async def _retrieve_for_plan(
        prompt: str,
        skill_description: str,
        plan: Any,
    ) -> dict[str, Any]:
        return await retrieve_entities_for_skill(
            data_func,
            prompt,
            skill_description,
            mode=plan.mode,
            query_overrides=plan.query_overrides,
        )

    def _format_skill_resume_answers(answers: dict[str, Any]) -> str:
        lines: list[str] = []
        for key, value in (answers or {}).items():
            label = str(key or "").strip()
            if not label:
                continue
            if isinstance(value, list):
                rendered = ", ".join(
                    str(item).strip() for item in value if str(item).strip()
                )
            else:
                rendered = str(value or "").strip()
            if rendered:
                lines.append(f"- {label}: {rendered}")
        return "\n".join(lines)

    def _skill_prompt(
        prompt: str,
        *,
        user_addendum: str = "",
        addendum_heading: str = "User-supplied missing input",
        artifact_block: str = "",
    ) -> str:
        parts = [str(prompt or "").strip()]
        if user_addendum.strip():
            parts.append(f"{addendum_heading}:\n" + user_addendum.strip())
        if artifact_block.strip():
            parts.append(artifact_block.strip())
        return "\n\n".join(part for part in parts if part)

    def _resolve_invoke_context_artifacts(
        mgr: Any,
        refs: list[ContextArtifactRef],
    ) -> tuple[list[Any], list[str], str, list[dict[str, Any]]]:
        if not refs:
            return [], [], "", []
        get_artifact_path = getattr(mgr, "get_artifact_path", None)
        if get_artifact_path is None:
            raise HTTPException(
                503,
                "Skill manager does not support context artifact resolution",
            )
        resolved, errors = resolve_context_artifacts(
            workspace_dir(),
            refs,
            get_artifact_path=get_artifact_path,
        )
        artifact_block = format_context_artifacts_prompt_block(resolved)
        input_artifacts = to_input_artifacts_payload(resolved)
        return resolved, errors, artifact_block, input_artifacts

    def _merge_context_artifacts_extras(
        extras: dict[str, Any],
        *,
        resolved: list[Any],
        input_artifacts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not resolved:
            return extras
        merged = dict(extras)
        merged["context_artifacts"] = [artifact.model_dump() for artifact in resolved]
        merged["input_artifacts"] = input_artifacts
        return merged

    def _skill_response_with_run(
        mgr: Any,
        result: Any,
        *,
        runtime_mode: str,
        retrieval: dict[str, Any],
    ) -> dict[str, Any]:
        body = _skill_response_payload(
            result,
            runtime_mode=runtime_mode,
            retrieval=retrieval,
        )
        if result.run_id:
            run = mgr.get_run(workspace_dir(), result.skill, result.run_id)
            if run is not None:
                body["run"] = _project_skill_run_payload(mgr, run)
        return body

    def _require_chain_skills(mgr: Any, spec: ChainSpec) -> dict[str, Any]:
        skills_by_name = {step.skill: mgr.get_skill(step.skill) for step in spec.steps}
        missing_skills = [
            name for name, skill in skills_by_name.items() if skill is None
        ]
        if missing_skills:
            raise HTTPException(
                404,
                f"Unknown skill(s): {', '.join(sorted(set(missing_skills)))}",
            )
        return skills_by_name

    def _chain_prompt(spec: ChainSpec, *, user_addendum: str = "") -> str:
        parts = [spec.prompt, *(step.prompt for step in spec.steps)]
        if user_addendum.strip():
            parts.append("User-supplied missing input:\n" + user_addendum.strip())
        return "\n\n".join(part for part in parts if part)

    def _chain_description(skills_by_name: dict[str, Any]) -> str:
        return "\n".join(
            skill.frontmatter.description
            for skill in skills_by_name.values()
            if skill is not None
        )

    async def _prepare_chain_execution(
        mgr: Any,
        spec: ChainSpec,
        payload: Any,
    ) -> tuple[dict[str, Any], dict[str, Any], Callable[..., dict[str, Any]], Callable[..., Awaitable[dict[str, Any]]]]:
        skills_by_name = _require_chain_skills(mgr, spec)
        user_addendum = str(getattr(payload, "user_addendum", "") or "").strip()
        chain_prompt = _chain_prompt(spec, user_addendum=user_addendum)
        plan = resolve_plan_from_store(query_settings_store, chain_prompt, payload=payload)
        retrieval = await _retrieve_for_plan(
            chain_prompt,
            _chain_description(skills_by_name),
            plan,
        )
        extras = (
            {"user_supplied_context": {"resume_notes": user_addendum}}
            if user_addendum
            else None
        )
        context = build_briefing_context(
            workspace_dir(),
            plan=plan,
            retrieval=retrieval,
            entity_types=None,
            extras=extras,
            slice_fn=slice_workspace_entities,
        )
        return (
            context,
            retrieval_metadata_from_plan(plan, retrieval_result=retrieval),
            make_slice_fn(
                workspace_dir(),
                plan=plan,
                retrieval_chunk_ids=retrieval.get("chunk_ids"),
                slice_fn=slice_workspace_entities,
            ),
            make_retrieve_fn(
                data_func,
                plan=plan,
                retrieve_impl=retrieve_entities_for_skill,
            ),
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
        frontmatter_mode = skill.frontmatter.runtime_mode if skill is not None else "legacy"
        effective_mode = resolve_skill_runtime_mode(frontmatter_mode)
        user_addendum = str(payload.user_addendum or "").strip()
        resolved_artifacts, artifact_errors, artifact_block, input_artifacts = (
            _resolve_invoke_context_artifacts(mgr, payload.context_artifacts)
        )
        if artifact_errors:
            raise HTTPException(400, "; ".join(artifact_errors))
        effective_prompt = _skill_prompt(
            payload.prompt,
            user_addendum=user_addendum,
            addendum_heading="User-supplied context",
            artifact_block=artifact_block,
        )

        plan = resolve_plan_from_store(
            query_settings_store,
            effective_prompt,
            payload=payload,
            skip_coverage_boost=skill_skips_coverage_boost(skill),
        )
        invoke_extras: dict[str, Any] = {}
        if user_addendum:
            invoke_extras = {
                "user_supplied_context": {"first_run_notes": user_addendum},
            }
        invoke_extras = _merge_context_artifacts_extras(
            invoke_extras,
            resolved=resolved_artifacts,
            input_artifacts=input_artifacts,
        )
        invoke_extras["retrieval_plan_limits"] = {
            "max_kg_entities_per_type": plan.briefing.max_entities_per_type,
            "max_kg_chunks_per_entity": plan.briefing.max_chunks_per_entity,
            "max_kg_relationships_per_entity": plan.briefing.max_relationships_per_entity,
            "max_chunk_content_chars": plan.briefing.max_chunk_content_chars,
            "max_kg_chunks": int(plan.query_overrides.get("top_k") or 0),
            "coverage_boost_applied": plan.coverage_boost_applied,
        }
        if effective_mode == "tools":
            try:
                result = await mgr.invoke(
                    name,
                    workspace=workspace_name(),
                    user_prompt=effective_prompt,
                    entity_payload=invoke_extras,
                    llm=llm_func,
                    workspace_root=workspace_dir(),
                    slice_fn=make_slice_fn(
                        workspace_dir(),
                        plan=plan,
                        slice_fn=slice_workspace_entities,
                    ),
                    retrieve_fn=make_retrieve_fn(
                        data_func,
                        plan=plan,
                        retrieve_impl=retrieve_entities_for_skill,
                    ),
                )
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            return JSONResponse(
                _skill_response_with_run(
                    mgr,
                    result,
                    runtime_mode="tools",
                    retrieval=retrieval_metadata_from_plan(plan),
                )
            )

        retrieval = await _retrieve_for_plan(effective_prompt, skill_desc, plan)
        context = build_briefing_context(
            workspace_dir(),
            plan=plan,
            retrieval=retrieval,
            entity_types=payload.entity_types,
            slice_fn=slice_workspace_entities,
        )
        if invoke_extras:
            context = {**context, **invoke_extras}
        try:
            result = await mgr.invoke(
                name,
                workspace=workspace_name(),
                user_prompt=effective_prompt,
                entity_payload=context,
                llm=llm_func,
                workspace_root=workspace_dir(),
            )
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return JSONResponse(
            _skill_response_with_run(
                mgr,
                result,
                runtime_mode="legacy",
                retrieval=retrieval_metadata_from_plan(plan, retrieval_result=retrieval),
            )
        )

    @app.post("/api/ui/skills/{name}/runs/{run_id}/resume", tags=["theseus-ui"])
    async def resume_skill_run_route(
        name: str,
        run_id: str,
        payload: SkillRunRepeatPayload = Body(...),
    ) -> JSONResponse:
        if llm_func is None:
            raise HTTPException(
                503,
                "Skill invocation requires an llm_func; server was started without one",
            )
        mgr = manager_factory()
        skill = mgr.get_skill(name)
        if skill is None:
            raise HTTPException(404, f"Unknown skill: {name}")
        run = mgr.get_run(workspace_dir(), name, run_id)
        if run is None:
            raise HTTPException(404, f"Unknown run: {name}/{run_id}")
        projected = _project_skill_run_payload(mgr, run)
        if not projected.get("can_resume"):
            raise HTTPException(409, "Run does not require user input")

        answer_text = _format_skill_resume_answers(payload.answers)
        user_addendum = str(payload.user_addendum or "").strip() or answer_text
        if not user_addendum:
            raise HTTPException(400, "user_addendum or answers required")

        resolved_artifacts, artifact_errors, artifact_block, input_artifacts = (
            _resolve_invoke_context_artifacts(mgr, payload.context_artifacts)
        )
        if artifact_errors:
            raise HTTPException(400, "; ".join(artifact_errors))

        original_prompt = str(
            ((projected.get("metadata") or {}).get("user_prompt") or "")
        ).strip()
        effective_prompt = _skill_prompt(
            original_prompt,
            user_addendum=user_addendum,
            artifact_block=artifact_block,
        )
        missing_inputs = list(projected.get("missing_inputs") or [])
        skill_desc = skill.frontmatter.description
        frontmatter_mode = skill.frontmatter.runtime_mode
        effective_mode = resolve_skill_runtime_mode(frontmatter_mode)

        plan = resolve_plan_from_store(
            query_settings_store,
            effective_prompt,
            payload=payload,
            skip_coverage_boost=skill_skips_coverage_boost(skill),
        )
        resume_extras = {
            "user_supplied_context": {
                "resume_notes": user_addendum,
                "missing_inputs": missing_inputs,
                "answers": payload.answers,
            }
        }
        resume_extras = _merge_context_artifacts_extras(
            resume_extras,
            resolved=resolved_artifacts,
            input_artifacts=input_artifacts,
        )
        if effective_mode == "tools":
            try:
                result = await mgr.invoke(
                    name,
                    workspace=workspace_name(),
                    user_prompt=effective_prompt,
                    entity_payload=resume_extras,
                    llm=llm_func,
                    workspace_root=workspace_dir(),
                    slice_fn=make_slice_fn(
                        workspace_dir(),
                        plan=plan,
                        slice_fn=slice_workspace_entities,
                    ),
                    retrieve_fn=make_retrieve_fn(
                        data_func,
                        plan=plan,
                        retrieve_impl=retrieve_entities_for_skill,
                    ),
                )
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            return JSONResponse(
                _skill_response_with_run(
                    mgr,
                    result,
                    runtime_mode="tools",
                    retrieval=retrieval_metadata_from_plan(plan),
                )
            )

        retrieval = await _retrieve_for_plan(effective_prompt, skill_desc, plan)
        context = build_briefing_context(
            workspace_dir(),
            plan=plan,
            retrieval=retrieval,
            entity_types=payload.entity_types,
            extras=resume_extras,
            slice_fn=slice_workspace_entities,
        )
        try:
            result = await mgr.invoke(
                name,
                workspace=workspace_name(),
                user_prompt=effective_prompt,
                entity_payload=context,
                llm=llm_func,
                workspace_root=workspace_dir(),
            )
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return JSONResponse(
            _skill_response_with_run(
                mgr,
                result,
                runtime_mode="legacy",
                retrieval=retrieval_metadata_from_plan(plan, retrieval_result=retrieval),
            )
        )

    @app.post("/api/ui/skill-chains/invoke", tags=["theseus-ui"])
    async def invoke_skill_chain_route(
        payload: SkillChainInvokePayload = Body(...),
    ) -> JSONResponse:
        if llm_func is None:
            raise HTTPException(
                503,
                "Skill-chain invocation requires an llm_func; server was started without one",
            )
        mgr = manager_factory()
        try:
            spec = payload.resolved_spec()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        context, retrieval, slice_fn, retrieve_fn = await _prepare_chain_execution(
            mgr,
            spec,
            payload,
        )
        try:
            result = await mgr.invoke_chain(
                spec,
                workspace=workspace_name(),
                entity_payload=context,
                llm=llm_func,
                workspace_root=workspace_dir(),
                slice_fn=slice_fn,
                retrieve_fn=retrieve_fn,
            )
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "chain": _project_chain_payload(mgr, result.model_dump()),
                "retrieval": retrieval,
            }
        )

    @app.post("/api/ui/skill-chains/plan", tags=["theseus-ui"])
    async def plan_skill_chain_route(
        payload: SkillChainPlanPayload = Body(...),
    ) -> JSONResponse:
        mgr = manager_factory()
        try:
            plan = mgr.plan_chain(
                prompt=payload.prompt,
                outcome=payload.outcome,
                max_steps=payload.max_steps,
                include_rendering=payload.include_rendering,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "plan": plan.model_dump(),
            }
        )

    @app.post("/api/ui/skill-chains/invoke-planned", tags=["theseus-ui"])
    async def invoke_planned_skill_chain_route(
        payload: SkillChainPlanPayload = Body(...),
    ) -> JSONResponse:
        if llm_func is None:
            raise HTTPException(
                503,
                "Skill-chain invocation requires an llm_func; server was started without one",
            )
        mgr = manager_factory()
        try:
            plan = mgr.plan_chain(
                prompt=payload.prompt,
                outcome=payload.outcome,
                max_steps=payload.max_steps,
                include_rendering=payload.include_rendering,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        context, retrieval, slice_fn, retrieve_fn = await _prepare_chain_execution(
            mgr,
            plan.spec,
            payload,
        )
        try:
            result = await mgr.invoke_chain(
                plan.spec,
                workspace=workspace_name(),
                entity_payload=context,
                llm=llm_func,
                workspace_root=workspace_dir(),
                slice_fn=slice_fn,
                retrieve_fn=retrieve_fn,
            )
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "plan": plan.model_dump(),
                "chain": _project_chain_payload(mgr, result.model_dump()),
                "retrieval": retrieval,
            }
        )

    @app.post("/api/ui/skill-chains/{chain_id}/rerun", tags=["theseus-ui"])
    async def rerun_skill_chain_route(
        chain_id: str,
        payload: Optional[SkillChainRepeatPayload] = Body(None),
    ) -> JSONResponse:
        if llm_func is None:
            raise HTTPException(503, "Skill-chain rerun requires an llm_func")
        payload = payload or SkillChainRepeatPayload()
        mgr = manager_factory()
        chain = mgr.get_chain_run(workspace_dir(), chain_id)
        if chain is None:
            raise HTTPException(404, f"Unknown chain: {chain_id}")
        spec = ChainSpec.model_validate(chain.get("spec") or {})
        context, retrieval, slice_fn, retrieve_fn = await _prepare_chain_execution(
            mgr,
            spec,
            payload,
        )
        result = await mgr.invoke_chain(
            spec,
            workspace=workspace_name(),
            entity_payload=context,
            llm=llm_func,
            workspace_root=workspace_dir(),
            slice_fn=slice_fn,
            retrieve_fn=retrieve_fn,
            source_chain_id=chain_id,
            mode="rerun",
        )
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "chain": _project_chain_payload(mgr, result.model_dump()),
                "retrieval": retrieval,
            }
        )

    @app.post("/api/ui/skill-chains/{chain_id}/resume", tags=["theseus-ui"])
    async def resume_skill_chain_route(
        chain_id: str,
        payload: Optional[SkillChainRepeatPayload] = Body(None),
    ) -> JSONResponse:
        if llm_func is None:
            raise HTTPException(503, "Skill-chain resume requires an llm_func")
        payload = payload or SkillChainRepeatPayload()
        mgr = manager_factory()
        chain = mgr.get_chain_run(workspace_dir(), chain_id)
        if chain is None:
            raise HTTPException(404, f"Unknown chain: {chain_id}")
        state = ChainRunState.model_validate(chain)
        context, retrieval, slice_fn, retrieve_fn = await _prepare_chain_execution(
            mgr,
            state.spec,
            payload,
        )
        user_addendum = payload.user_addendum.strip()
        missing_inputs = list(
            state.input_request.get("missing_inputs") or state.missing_inputs or []
        )
        resume_context: dict[str, Any] = {}
        if user_addendum:
            resume_context["resume_notes"] = user_addendum
        if missing_inputs:
            resume_context["missing_inputs"] = missing_inputs
        resume_step_id = (
            payload.from_step_id
            or str(state.input_request.get("resume_step_id") or "").strip()
        )
        if resume_step_id:
            resume_context["resume_step_id"] = resume_step_id
        if resume_context:
            context["user_supplied_context"] = {
                **(context.get("user_supplied_context") or {}),
                **resume_context,
            }
        try:
            result = await mgr.resume_chain(
                state,
                workspace_root=workspace_dir(),
                entity_payload=context,
                llm=llm_func,
                slice_fn=slice_fn,
                retrieve_fn=retrieve_fn,
                from_step_id=payload.from_step_id,
                resume_notes=user_addendum,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "chain": _project_chain_payload(mgr, result.model_dump()),
                "retrieval": retrieval,
            }
        )


def register_skill_run_ui_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
    manager_factory: Callable[[], Any] = get_skill_manager,
) -> None:
    """Register skill run, artifact, and chunk-preview endpoints."""

    @app.get("/api/ui/skills/{name}/runs", tags=["theseus-ui"])
    async def list_skill_runs_route(name: str, limit: int = 50) -> JSONResponse:
        mgr = manager_factory()
        runs = mgr.list_runs(workspace_dir(), skill_name=name, limit=limit)
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "skill": name,
                "runs": runs,
            }
        )

    @app.get("/api/ui/skill-chains", tags=["theseus-ui"])
    async def list_skill_chains_route(limit: int = 50) -> JSONResponse:
        mgr = manager_factory()
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "chains": mgr.list_chain_runs(workspace_dir(), limit=limit),
            }
        )

    @app.get("/api/ui/skill-chains/{chain_id}", tags=["theseus-ui"])
    async def get_skill_chain_route(chain_id: str) -> JSONResponse:
        mgr = manager_factory()
        chain = mgr.get_chain_run(workspace_dir(), chain_id)
        if chain is None:
            raise HTTPException(404, f"Unknown chain: {chain_id}")
        return JSONResponse(_project_chain_payload(mgr, chain))

    @app.get("/api/ui/skills/{name}/runs/trash", tags=["theseus-ui"])
    async def list_skill_run_trash_route(name: str, limit: int = 50) -> JSONResponse:
        mgr = manager_factory()
        runs = mgr.list_trashed_runs(workspace_dir(), skill_name=name, limit=limit)
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "skill": name,
                "runs": runs,
            }
        )

    @app.get("/api/ui/skills/{name}/runs/{run_id}", tags=["theseus-ui"])
    async def get_skill_run_route(name: str, run_id: str) -> JSONResponse:
        mgr = manager_factory()
        run = mgr.get_run(workspace_dir(), name, run_id)
        if run is None:
            raise HTTPException(404, f"Unknown run: {name}/{run_id}")
        return JSONResponse(_project_skill_run_payload(mgr, run))

    @app.get(
        "/api/ui/skills/{name}/runs/{run_id}/reasoning",
        tags=["theseus-ui"],
    )
    async def get_skill_run_reasoning_route(name: str, run_id: str) -> JSONResponse:
        from src.skills.reasoning import build_reasoning_view

        mgr = manager_factory()
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

    @app.post(
        "/api/ui/skills/{name}/runs/{run_id}/artifacts/render",
        tags=["theseus-ui"],
    )
    async def rerender_skill_run_artifacts_route(name: str, run_id: str) -> JSONResponse:
        mgr = manager_factory()
        skill = mgr.get_skill(name)
        if skill is None:
            raise HTTPException(404, f"Unknown skill: {name}")
        run = mgr.get_run(workspace_dir(), name, run_id)
        if run is None:
            raise HTTPException(404, f"Unknown run: {name}/{run_id}")
        run_dir = _run_dir_for_skill_run(workspace_dir(), name, run_id)
        if run_dir is None:
            raise HTTPException(404, f"Unknown run: {name}/{run_id}")

        def _rerender() -> dict[str, Any]:
            before = [
                row
                for row in mgr.list_deliverables(workspace_dir(), limit=5000)
                if row.get("skill") == name and row.get("run_id") == run_id
            ]
            before_names = {str(row.get("filename") or "") for row in before}
            auto_emit_artifacts(skill, run_dir)
            refreshed = mgr.get_run(workspace_dir(), name, run_id)
            deliverables = [
                row
                for row in mgr.list_deliverables(workspace_dir(), limit=5000)
                if row.get("skill") == name and row.get("run_id") == run_id
            ]
            created = [
                row for row in deliverables if str(row.get("filename") or "") not in before_names
            ]
            return {
                "run": refreshed,
                "deliverables": deliverables,
                "created": created,
            }

        result = await asyncio.to_thread(_rerender)
        deliverables = result["deliverables"]
        if not deliverables:
            raise HTTPException(409, "No Studio deliverables were emitted for this run")
        refreshed_run = result["run"] or run
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "skill": name,
                "run_id": run_id,
                "deliverable_count": len(deliverables),
                "created_count": len(result["created"]),
                "deliverables": deliverables,
                "created": result["created"],
                "artifacts": refreshed_run.get("artifacts") or [],
            }
        )

    @app.get("/api/ui/chunks/{chunk_id}", tags=["theseus-ui"])
    async def get_chunk_route(chunk_id: str) -> JSONResponse:
        if not chunk_id or len(chunk_id) > 128 or "/" in chunk_id or "\\" in chunk_id:
            raise HTTPException(400, "Invalid chunk id")

        chunks_path = workspace_dir() / "kv_store_text_chunks.json"
        if not chunks_path.exists():
            raise HTTPException(404, "No text-chunk store in this workspace")

        chunk = await asyncio.to_thread(get_text_chunk, chunks_path, chunk_id)
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
        mgr = manager_factory()
        ok = mgr.purge_run(workspace_dir(), name, run_id)
        if not ok:
            raise HTTPException(404, f"Unknown or unsafe run id: {name}/{run_id}")
        return JSONResponse({"removed": run_id, "purged": True})

    @app.delete("/api/ui/skills/{name}/runs/trash", tags=["theseus-ui"])
    async def empty_skill_run_trash_route(name: str) -> JSONResponse:
        mgr = manager_factory()
        result = mgr.purge_trashed_runs(workspace_dir(), skill_name=name)
        return JSONResponse(
            {
                "skill": name,
                "workspace": get_settings().workspace,
                **result,
            }
        )

    @app.post("/api/ui/skills/{name}/runs/trash/restore", tags=["theseus-ui"])
    async def restore_skill_run_route(name: str, payload: dict[str, Any]) -> JSONResponse:
        mgr = manager_factory()
        trash_ids = [
            str(item.get("trash_id") or "")
            for item in (payload.get("runs") or [])
            if isinstance(item, dict)
        ]
        trash_ids = [trash_id for trash_id in trash_ids if trash_id]
        if not trash_ids:
            raise HTTPException(400, "No run trash ids provided")
        result = mgr.restore_trashed_runs(workspace_dir(), trash_ids)
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "skill": name,
                "restored": result.get("restored") or [],
                "missing": result.get("missing") or [],
                "conflicts": result.get("conflicts") or [],
                "restored_count": len(result.get("restored") or []),
            }
        )

    @app.get(
        "/api/ui/skills/{name}/runs/{run_id}/artifacts/{artifact_path:path}",
        tags=["theseus-ui"],
    )
    async def download_skill_run_artifact_route(
        name: str,
        run_id: str,
        artifact_path: str,
    ) -> FileResponse:
        mgr = manager_factory()
        path = mgr.get_artifact_path(workspace_dir(), name, run_id, artifact_path)
        if path is None:
            raise HTTPException(
                404,
                f"Artifact not found: {name}/{run_id}/{artifact_path}",
            )
        return FileResponse(
            path,
            media_type=resolve_artifact_mime(path.name),
            filename=path.name,
        )

def register_skill_ui_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
    data_func: Optional[QueryDataFunc],
    llm_func: Optional[LlmFunc],
    set_env_var: Callable[[str, str], None] | None = None,
    query_settings_store: Any | None = None,
) -> None:
    """Register skill, run, Studio, and chunk-preview UI endpoints."""

    if query_settings_store is None:
        from src.server.chat_routes import QuerySettingsStore

        query_settings_store = QuerySettingsStore(
            workspace_dir=workspace_dir,
            settings_provider=get_settings,
        )
    current_workspace = lambda: get_settings().workspace

    register_skill_settings_ui_routes(
        app,
        query_settings_store=query_settings_store,
        workspace_name=current_workspace,
        set_env_var=set_env_var,
    )
    register_skill_catalog_ui_routes(app, manager_factory=get_skill_manager)
    register_skill_invoke_ui_routes(
        app,
        workspace_dir=workspace_dir,
        query_settings_store=query_settings_store,
        data_func=data_func,
        llm_func=llm_func,
        workspace_name=current_workspace,
        manager_factory=get_skill_manager,
    )
    register_skill_run_ui_routes(
        app,
        workspace_dir=workspace_dir,
        manager_factory=get_skill_manager,
    )
    from src.server.studio_routes import register_studio_ui_routes

    register_studio_ui_routes(app, workspace_dir=workspace_dir)


__all__ = [
    "register_skill_catalog_ui_routes",
    "register_skill_invoke_ui_routes",
    "register_skill_run_ui_routes",
    "register_skill_settings_ui_routes",
    "register_skill_ui_routes",
]
