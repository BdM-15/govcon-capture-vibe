"""Workspace management routes for the Project Theseus UI."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from src.core import reset_settings
from src.server.workspace_admin import (
    WorkspaceDeleteScope,
    WorkspaceSwitch,
    WipeAllScope,
    delete_workspace_sync,
    discover_workspaces,
    ensure_active_storage_workspace,
    self_restart,
    set_env_var,
    wipe_all_workspaces_sync,
    workspace_inventory,
)
from src.server.storage_counts import safe_count_json_keys

logger = logging.getLogger(__name__)

_SAFE_WS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def register_workspace_ui_routes(
    app: FastAPI,
    *,
    workspace_name: Callable[[], str],
    working_dir: Callable[[], Path],
    graph_storage: Callable[[], str],
    set_env_var_func: Callable[[str, str], None] = set_env_var,
    schedule_restart: Callable[[float], None] | None = None,
    inventory_func: Callable[..., dict[str, Any]] = workspace_inventory,
    delete_workspace_func: Callable[..., dict[str, Any]] = delete_workspace_sync,
    ensure_active_workspace: Callable[[str], None] = ensure_active_storage_workspace,
) -> None:
    """Register workspace list, switch, inventory, delete, wipe, and restart routes."""

    def _schedule_restart(delay: float) -> None:
        if schedule_restart is not None:
            schedule_restart(delay)
        else:
            asyncio.get_event_loop().call_later(delay, self_restart)

    @app.get("/api/ui/workspaces", tags=["theseus-ui"])
    async def list_workspaces() -> JSONResponse:
        """List discovered workspace directories under rag_storage/."""
        return JSONResponse(
            {
                "active": workspace_name(),
                "workspaces": discover_workspaces(working_dir()),
            }
        )

    @app.post("/api/ui/workspaces/switch", tags=["theseus-ui"])
    async def switch_workspace(payload: WorkspaceSwitch) -> JSONResponse:
        """Persist WORKSPACE=<name> and schedule a graceful restart."""
        name = payload.name.strip()
        if not _SAFE_WS.match(name):
            raise HTTPException(400, "Invalid workspace name (use alphanumerics, _, -)")
        existing = {workspace["name"] for workspace in discover_workspaces(working_dir())}
        if not payload.create and name not in existing:
            raise HTTPException(404, f"Workspace '{name}' does not exist")
        working_dir().mkdir(parents=True, exist_ok=True)
        (working_dir() / name).mkdir(parents=True, exist_ok=True)
        try:
            set_env_var_func("WORKSPACE", name)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, f"Failed updating .env: {exc}") from exc
        _schedule_restart(0.75)
        logger.warning("Workspace switch requested -> '%s'. Restarting server...", name)
        return JSONResponse(
            {
                "status": "restarting",
                "workspace": name,
                "message": "Server is restarting. The UI will reconnect automatically.",
            }
        )

    @app.get("/api/ui/workspaces/inventory", tags=["theseus-ui"])
    async def workspaces_inventory() -> JSONResponse:
        """Per-workspace inventory: Neo4j node count, rag_storage size, inputs files."""
        result = await asyncio.to_thread(
            inventory_func,
            active_workspace=workspace_name(),
            graph_storage=graph_storage(),
        )
        return JSONResponse(result)

    @app.post("/api/ui/workspaces/{name}/delete", tags=["theseus-ui"])
    async def delete_workspace(name: str, scope: WorkspaceDeleteScope) -> JSONResponse:
        """Delete one workspace's selected buckets."""
        if not _SAFE_WS.match(name):
            raise HTTPException(400, "Invalid workspace name (use alphanumerics, _, -)")
        if not (scope.neo4j or scope.rag_storage or scope.inputs):
            raise HTTPException(
                400,
                "At least one scope (neo4j/rag_storage/inputs) must be true.",
            )
        if name == workspace_name():
            raise HTTPException(
                409,
                "Cannot delete the active workspace. Switch to another workspace first.",
            )
        logger.warning(
            "Deleting workspace '%s' (neo4j=%s, rag_storage=%s, inputs=%s)",
            name,
            scope.neo4j,
            scope.rag_storage,
            scope.inputs,
        )
        result = await asyncio.to_thread(
            delete_workspace_func,
            name,
            scope,
            graph_storage=graph_storage(),
        )
        return JSONResponse(result)

    @app.post("/api/ui/workspaces/wipe-all", tags=["theseus-ui"])
    async def wipe_all_workspaces(scope: WipeAllScope) -> JSONResponse:
        """Clean-slate wipe across every workspace. Requires confirm='DELETE ALL'."""
        if scope.confirm != "DELETE ALL":
            raise HTTPException(400, "Confirmation phrase must equal 'DELETE ALL'.")
        if not (scope.neo4j or scope.rag_storage or scope.inputs):
            raise HTTPException(
                400,
                "At least one scope (neo4j/rag_storage/inputs) must be true.",
            )

        logger.warning(
            "Wipe all workspaces requested (neo4j=%s, rag_storage=%s, inputs=%s)",
            scope.neo4j,
            scope.rag_storage,
            scope.inputs,
        )
        result = await asyncio.to_thread(
            wipe_all_workspaces_sync,
            scope,
            active_workspace=workspace_name(),
            graph_storage=graph_storage(),
            inventory_func=inventory_func,
            delete_workspace_func=delete_workspace_func,
            ensure_active_workspace=ensure_active_workspace,
        )
        _schedule_restart(0.75)
        result["restarting"] = True
        return JSONResponse(result)

    @app.post("/api/ui/restart", tags=["theseus-ui"])
    async def restart_server() -> JSONResponse:
        """Schedule a graceful self-restart of the server process."""
        _schedule_restart(0.75)
        logger.warning("Manual restart requested via Settings page.")
        return JSONResponse(
            {
                "status": "restarting",
                "workspace": workspace_name(),
                "message": "Server is restarting. The UI will reconnect automatically.",
            }
        )
