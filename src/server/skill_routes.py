"""Agent-skill UI routes for Project Theseus."""

import asyncio
import io
import json
import logging
from pathlib import Path
import zipfile
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from src.core import get_settings
from src.skills import get_skill_manager
from src.skills.context import (
    build_skill_briefing_book,
    retrieve_relevant_entities_for_skill,
)
from src.skills.skill_emitters import auto_emit_artifacts
from src.skills.runs import resolve_artifact_mime
from src.skills.settings import (
    SkillSettingsStore,
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
    [Optional[QueryDataFunc], str, str, str, int],
    Awaitable[dict[str, Any]],
]


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


class StudioArtifactDeleteItem(BaseModel):
    """One artifact selected for deletion from Studio."""

    skill: str = Field(..., min_length=1, max_length=128)
    run_id: str = Field(..., min_length=1, max_length=128)
    filename: str = Field(..., min_length=1, max_length=255)


class StudioArtifactDeletePayload(BaseModel):
    """Bulk deletion request for Studio artifacts."""

    artifacts: list[StudioArtifactDeleteItem] = Field(..., min_length=1, max_length=200)


class StudioArtifactZipPayload(BaseModel):
    """Bulk download request for Studio artifacts."""

    artifacts: list[StudioArtifactDeleteItem] = Field(..., min_length=1, max_length=200)


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
    settings_store: SkillSettingsStore,
    workspace_name: Callable[[], str] | None = None,
    set_env_var: Callable[[str, str], None] | None = None,
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
        frontmatter_mode = skill.frontmatter.runtime_mode if skill is not None else "legacy"
        effective_mode = resolve_skill_runtime_mode(frontmatter_mode)

        if effective_mode == "tools":
            def _tools_slice_workspace_entities(
                entity_types: Optional[list[str]],
                max_per_type: int,
                max_chunks_per_entity: int = 2,
                max_relationships_per_entity: int = 5,
                relevant_entity_names: Optional[set[str]] = None,
            ) -> dict[str, Any]:
                return _slice_workspace_entities(
                    entity_types,
                    min(max_per_type, payload.max_entities_per_type),
                    max_chunks_per_entity=min(
                        max_chunks_per_entity,
                        payload.max_chunks_per_entity,
                    ),
                    max_relationships_per_entity=min(
                        max_relationships_per_entity,
                        payload.max_relationships_per_entity,
                    ),
                    relevant_entity_names=relevant_entity_names,
                )

            async def _tools_retrieve_relevant_entities_for_skill(
                prompt: str,
                skill_description: str,
                mode: str,
                top_k: int,
            ) -> dict[str, Any]:
                return await _retrieve_relevant_entities_for_skill(
                    prompt,
                    skill_description,
                    payload.retrieval_mode,
                    min(top_k, payload.retrieval_top_k),
                )

            try:
                result = await mgr.invoke(
                    name,
                    workspace=workspace_name(),
                    user_prompt=payload.prompt,
                    entity_payload={},
                    llm=llm_func,
                    workspace_root=workspace_dir(),
                    slice_fn=_tools_slice_workspace_entities,
                    retrieve_fn=_tools_retrieve_relevant_entities_for_skill,
                )
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            return JSONResponse(
                _skill_response_payload(
                    result,
                    runtime_mode="tools",
                    retrieval={
                        "mode": payload.retrieval_mode,
                        "top_k": payload.retrieval_top_k,
                        "used": payload.retrieval_mode != "off",
                        "reason": "tools-mode runtime",
                        "max_entities_per_type": payload.max_entities_per_type,
                        "max_chunks_per_entity": payload.max_chunks_per_entity,
                        "max_relationships_per_entity": payload.max_relationships_per_entity,
                    },
                )
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
            _skill_response_payload(
                result,
                runtime_mode="legacy",
                retrieval=retrieval["metadata"],
            )
        )


def register_skill_run_ui_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
) -> None:
    """Register skill run, artifact, chunk-preview, and Studio endpoints."""

    @app.get("/api/ui/skills/{name}/runs", tags=["theseus-ui"])
    async def list_skill_runs_route(name: str, limit: int = 50) -> JSONResponse:
        mgr = get_skill_manager()
        runs = mgr.list_runs(workspace_dir(), skill_name=name, limit=limit)
        return JSONResponse(
            {
                "workspace": get_settings().workspace,
                "skill": name,
                "runs": runs,
            }
        )

    @app.get("/api/ui/skills/{name}/runs/{run_id}", tags=["theseus-ui"])
    async def get_skill_run_route(name: str, run_id: str) -> JSONResponse:
        mgr = get_skill_manager()
        run = mgr.get_run(workspace_dir(), name, run_id)
        if run is None:
            raise HTTPException(404, f"Unknown run: {name}/{run_id}")
        return JSONResponse(run)

    @app.get(
        "/api/ui/skills/{name}/runs/{run_id}/reasoning",
        tags=["theseus-ui"],
    )
    async def get_skill_run_reasoning_route(name: str, run_id: str) -> JSONResponse:
        from src.skills.reasoning import build_reasoning_view

        mgr = get_skill_manager()
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
        mgr = get_skill_manager()
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

        def _load_chunk() -> Optional[dict[str, Any]]:
            try:
                store = json.loads(chunks_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed reading text-chunk store: %s", exc)
                return None
            return store.get(chunk_id)

        chunk = await asyncio.to_thread(_load_chunk)
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
        mgr = get_skill_manager()
        ok = mgr.delete_run(workspace_dir(), name, run_id)
        if not ok:
            raise HTTPException(404, f"Unknown or unsafe run id: {name}/{run_id}")
        return JSONResponse({"removed": run_id})

    @app.get(
        "/api/ui/skills/{name}/runs/{run_id}/artifacts/{filename}",
        tags=["theseus-ui"],
    )
    async def download_skill_run_artifact_route(
        name: str,
        run_id: str,
        filename: str,
    ) -> FileResponse:
        mgr = get_skill_manager()
        path = mgr.get_artifact_path(workspace_dir(), name, run_id, filename)
        if path is None:
            raise HTTPException(404, f"Artifact not found: {name}/{run_id}/{filename}")
        return FileResponse(
            path,
            media_type=resolve_artifact_mime(path.name),
            filename=path.name,
        )

    @app.get("/api/ui/studio", tags=["theseus-ui"])
    async def list_studio_deliverables_route(limit: int = 500) -> JSONResponse:
        mgr = get_skill_manager()
        deliverables = await asyncio.to_thread(
            mgr.list_deliverables,
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
        mgr = get_skill_manager()
        artifacts = await asyncio.to_thread(
            mgr.list_trashed_artifacts,
            workspace_dir(),
            limit,
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
        mgr = get_skill_manager()
        refs = [item.model_dump() for item in payload.artifacts]

        def _build_zip() -> tuple[bytes, list[dict[str, str]], list[dict[str, str]]]:
            buffer = io.BytesIO()
            included: list[dict[str, str]] = []
            missing: list[dict[str, str]] = []
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for ref in refs:
                    path = mgr.get_artifact_path(
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
        mgr = get_skill_manager()
        result = await asyncio.to_thread(
            mgr.trash_artifacts,
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
        mgr = get_skill_manager()
        result = await asyncio.to_thread(
            mgr.restore_trashed_artifacts,
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


def register_skill_ui_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
    data_func: Optional[QueryDataFunc],
    llm_func: Optional[LlmFunc],
    set_env_var: Callable[[str, str], None] | None = None,
) -> None:
    """Register skill, run, Studio, and chunk-preview UI endpoints."""

    settings_store = SkillSettingsStore(workspace_dir)
    current_workspace = lambda: get_settings().workspace

    register_skill_settings_ui_routes(
        app,
        settings_store=settings_store,
        workspace_name=current_workspace,
        set_env_var=set_env_var,
    )
    register_skill_catalog_ui_routes(app, manager_factory=get_skill_manager)
    register_skill_invoke_ui_routes(
        app,
        workspace_dir=workspace_dir,
        settings_store=settings_store,
        data_func=data_func,
        llm_func=llm_func,
        workspace_name=current_workspace,
        manager_factory=get_skill_manager,
    )
    register_skill_run_ui_routes(app, workspace_dir=workspace_dir)


__all__ = [
    "register_skill_catalog_ui_routes",
    "register_skill_invoke_ui_routes",
    "register_skill_run_ui_routes",
    "register_skill_settings_ui_routes",
    "register_skill_ui_routes",
]
