"""Admin/settings routes for dashboard stats and vendored MCP management."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.core import get_settings
from src.core.env import env_int
from src.ontology.schema import VALID_ENTITY_TYPES, VALID_RELATIONSHIP_TYPES
from src.server.workspace_routes import safe_count_json_keys
from src.utils.time_utils import now_local_iso

logger = logging.getLogger(__name__)

_STACK_CACHE: Optional[dict[str, Optional[str]]] = None
_RELEASE_VERSION_CACHE: Optional[str] = None
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAFE_MCP_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_ENV_KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class McpKeyUpdate(BaseModel):
    """Body for POST /api/ui/mcps/{name}/keys."""

    keys: dict[str, str] = Field(
        default_factory=dict,
        description="env-var name -> value pairs (must be declared by the MCP)",
    )
    restart: bool = Field(
        default=True,
        description="Schedule a graceful self-restart so subprocess env updates",
    )


def stack_versions() -> dict[str, Optional[str]]:
    """Read installed package versions for the engine stack."""
    global _STACK_CACHE  # noqa: PLW0603
    if _STACK_CACHE is not None:
        return _STACK_CACHE
    from importlib.metadata import PackageNotFoundError, version

    versions: dict[str, Optional[str]] = {}
    for key, distribution in (
        ("lightrag", "lightrag-hku"),
        ("raganything", "raganything"),
        ("mineru", "mineru"),
        ("transformers", "transformers"),
    ):
        try:
            versions[key] = version(distribution)
        except PackageNotFoundError:
            try:
                versions[key] = version(key)
            except PackageNotFoundError:
                versions[key] = None
    _STACK_CACHE = versions
    return versions


def release_version() -> str:
    """Resolve the current Theseus release version for UI display."""
    global _RELEASE_VERSION_CACHE  # noqa: PLW0603
    if _RELEASE_VERSION_CACHE is not None:
        return _RELEASE_VERSION_CACHE

    env_version = os.getenv("THESEUS_RELEASE_VERSION", "").strip()
    if env_version:
        _RELEASE_VERSION_CACHE = env_version
        return env_version

    try:
        completed = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        tag = completed.stdout.strip()
        if tag:
            _RELEASE_VERSION_CACHE = tag
            return tag
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    return "v0.0.0"


def ui_chat_history_pairs() -> int:
    """Resolve the per-query conversation-history cap in user+assistant pairs."""
    return env_int("UI_CHAT_HISTORY_TURNS", 20, 0)


def _now_iso() -> str:
    return now_local_iso(timespec="seconds")


def gather_stats(
    *,
    workspace_dir: Callable[[], Path],
    chats_dir: Callable[[], Path],
    settings_provider: Callable[[], Any] = get_settings,
    graph_storage: Callable[[], str] = lambda: "NetworkXStorage",
    now: Callable[[], str] = _now_iso,
    stack_versions_func: Callable[[], dict[str, Optional[str]]] = stack_versions,
    release_version_func: Callable[[], str] = release_version,
    count_json_keys: Callable[[Path], int] = safe_count_json_keys,
) -> dict[str, Any]:
    """Build dashboard rollup metrics for the active workspace."""
    settings = settings_provider()
    workspace = workspace_dir()
    inference_only_relationship_types = {"REQUIRES", "ENABLED_BY", "RESPONSIBLE_FOR"}
    return {
        "workspace": settings.workspace,
        "graph_storage": graph_storage(),
        "working_dir": str(workspace),
        "documents": count_json_keys(workspace / "kv_store_doc_status.json"),
        "entities": count_json_keys(workspace / "vdb_entities.json"),
        "relationships": count_json_keys(workspace / "vdb_relationships.json"),
        "chunks": count_json_keys(workspace / "vdb_chunks.json"),
        "chats": sum(1 for _ in chats_dir().glob("*.json")),
        "chat": {
            "history_pairs_cap": ui_chat_history_pairs(),
        },
        "version": release_version_func(),
        "ontology": {
            "entity_type_count": len(VALID_ENTITY_TYPES),
            "relationship_type_count": len(VALID_RELATIONSHIP_TYPES),
            "extraction_relationship_type_count": len(
                VALID_RELATIONSHIP_TYPES - inference_only_relationship_types
            ),
        },
        "models": {
            "extraction": settings.extraction_llm_name,
            "reasoning": settings.reasoning_llm_name,
            "embedding": settings.embedding_model,
            "rerank": settings.rerank_model if settings.enable_rerank else None,
            "rerank_enabled": settings.enable_rerank,
        },
        "stack": stack_versions_func(),
        "timestamp": now(),
    }


def register_dashboard_stats_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
    chats_dir: Callable[[], Path],
    settings_provider: Callable[[], Any] = get_settings,
    graph_storage: Callable[[], str] = lambda: "NetworkXStorage",
    now: Callable[[], str] = _now_iso,
) -> None:
    """Register dashboard stats endpoints."""

    @app.get("/api/ui/stats", tags=["theseus-ui"])
    async def ui_stats() -> JSONResponse:
        """Return dashboard rollup metrics for the active workspace."""
        return JSONResponse(
            gather_stats(
                workspace_dir=workspace_dir,
                chats_dir=chats_dir,
                settings_provider=settings_provider,
                graph_storage=graph_storage,
                now=now,
            )
        )


def _mcps_root() -> Path:
    return Path.cwd() / "tools" / "mcps"


def _mask_secret(value: str) -> str:
    """Show first 4 + last 2, never the middle. Empty stays empty."""
    if not value:
        return ""
    if len(value) <= 8:
        return value[0] + "***"
    return f"{value[:4]}***{value[-2:]}"


def _env_status(name: str) -> dict[str, Any]:
    value = os.environ.get(name, "")
    return {"name": name, "set": bool(value), "masked": _mask_secret(value)}


def register_mcp_ui_routes(
    app: FastAPI,
    *,
    set_env_var: Callable[[str, str], None],
    schedule_restart: Callable[[float], None],
) -> None:
    """Register MCP inventory, key-management, and test-connection routes."""

    @app.get("/api/ui/mcps", tags=["theseus-ui"])
    async def list_mcps_route() -> JSONResponse:
        """List vendored MCP servers + their env-var status."""
        from src.skills.mcp_client import discover_manifests

        manifests = discover_manifests(_mcps_root())
        items: list[dict[str, Any]] = []
        for name in sorted(manifests):
            manifest = manifests[name]
            items.append(
                {
                    "name": manifest.name,
                    "description": manifest.description,
                    "command": manifest.command,
                    "env_required": [
                        _env_status(key) for key in manifest.env_required
                    ],
                    "env_optional": [
                        _env_status(key) for key in manifest.env_optional
                    ],
                    "missing_env": manifest.missing_env(),
                    "vendored_from": manifest.vendored_from,
                    "vendored_commit": manifest.vendored_commit,
                    "vendored_at": manifest.vendored_at,
                    "license": manifest.license,
                }
            )
        return JSONResponse({"mcps": items})

    @app.post("/api/ui/mcps/{name}/keys", tags=["theseus-ui"])
    async def update_mcp_keys_route(name: str, payload: McpKeyUpdate) -> JSONResponse:
        """Persist env vars for one MCP into .env, then schedule restart."""
        from src.skills.mcp_client import discover_manifests

        if not _SAFE_MCP_NAME.match(name):
            raise HTTPException(400, "Invalid MCP name")
        manifests = discover_manifests(_mcps_root())
        if name not in manifests:
            raise HTTPException(404, f"Unknown MCP: {name}")
        manifest = manifests[name]
        allowed = set(manifest.env_required) | set(manifest.env_optional)
        if not allowed:
            raise HTTPException(400, f"MCP {name!r} declares no env vars")
        bad = [key for key in payload.keys if key not in allowed]
        if bad:
            raise HTTPException(
                400,
                f"Keys not declared by MCP {name!r}: {bad}. "
                f"Allowed: {sorted(allowed)}",
            )
        invalid = [key for key in payload.keys if not _SAFE_ENV_KEY.match(key)]
        if invalid:
            raise HTTPException(400, f"Malformed env-var names: {invalid}")
        written: list[str] = []
        for key, value in payload.keys.items():
            try:
                set_env_var(key, value)
                written.append(key)
            except Exception as exc:
                raise HTTPException(500, f"Failed updating .env for {key}: {exc}") from exc
        if payload.restart and written:
            schedule_restart(0.75)
            logger.warning("MCP %s keys updated (%s) - restarting...", name, written)
            return JSONResponse(
                {
                    "status": "restarting",
                    "written": written,
                    "mcp": name,
                    "message": "Keys saved. Server is restarting; UI will reconnect.",
                }
            )
        return JSONResponse(
            {
                "status": "saved",
                "written": written,
                "mcp": name,
            }
        )

    @app.post("/api/ui/mcps/{name}/test", tags=["theseus-ui"])
    async def test_mcp_route(name: str) -> JSONResponse:
        """Spawn the MCP, complete handshake, and return tool inventory."""
        from src.skills.mcp_client import MCPError, MCPSession, discover_manifests

        if not _SAFE_MCP_NAME.match(name):
            raise HTTPException(400, "Invalid MCP name")
        manifests = discover_manifests(_mcps_root())
        if name not in manifests:
            raise HTTPException(404, f"Unknown MCP: {name}")
        session = MCPSession(manifests[name])
        try:
            try:
                await session.start()
            except MCPError as exc:
                return JSONResponse({"ok": False, "mcp": name, "error": str(exc)})
            tools = list(session.tools)
            return JSONResponse(
                {
                    "ok": True,
                    "mcp": name,
                    "tool_count": len(tools),
                    "sample_tools": [tool.name for tool in tools[:8]],
                }
            )
        finally:
            try:
                await session.shutdown()
            except Exception:  # noqa: BLE001 - best-effort reap
                logger.debug("MCP %s test shutdown raised", name, exc_info=True)


__all__ = [
    "McpKeyUpdate",
    "gather_stats",
    "register_dashboard_stats_routes",
    "register_mcp_ui_routes",
    "release_version",
    "stack_versions",
    "ui_chat_history_pairs",
]