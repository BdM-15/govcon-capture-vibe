"""Workspace admin models and pure operations used by the UI routes."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.core import reset_settings
from src.server.workspace_maintenance import DEFAULT_WORKSPACE_MAINTENANCE

logger = logging.getLogger(__name__)


class WorkspaceSwitch(BaseModel):
    """Body for POST /api/ui/workspaces/switch."""

    name: str = Field(..., min_length=1, max_length=64)
    create: bool = Field(default=False, description="Create the folder if it does not exist.")


class WorkspaceDeleteScope(BaseModel):
    """Which buckets of a workspace to delete. At least one must be true."""

    neo4j: bool = Field(default=False, description="Delete the workspace's Neo4j subgraph.")
    rag_storage: bool = Field(default=False, description="Delete rag_storage/<ws>/ (KV stores, VDBs, chats, log).")
    inputs: bool = Field(default=False, description="Delete inputs/<ws>/ source documents (irrecoverable).")


class WipeAllScope(BaseModel):
    """Clean-slate wipe. Requires the literal confirmation phrase."""

    neo4j: bool = Field(default=False)
    rag_storage: bool = Field(default=False)
    inputs: bool = Field(default=False)
    confirm: str = Field(..., description="Must equal 'DELETE ALL'.")


def discover_workspaces(working_dir: Path) -> list[dict[str, Any]]:
    """List candidate workspaces under the configured working directory."""
    return DEFAULT_WORKSPACE_MAINTENANCE.discover_workspaces(working_dir)


def set_env_var(key: str, value: str) -> None:
    """Update or append KEY=value in the project .env file."""
    env_path = Path.cwd() / ".env"
    lines: list[str] = []
    found = False
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            stripped = raw.lstrip()
            if stripped.startswith(f"{key}=") and not stripped.startswith("#"):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(raw)
    if not found:
        lines.append(f"{key}={value}")
    tmp = env_path.with_suffix(".env.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(env_path)
    os.environ[key] = value
    reset_settings()


def self_restart() -> None:
    """Re-exec the current python process with the same argv."""
    logger.warning("Re-execing process: %s %s", sys.executable, sys.argv)
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as exc:  # pragma: no cover
        logger.exception("Self-restart failed: %s", exc)
        os._exit(1)


def workspace_inventory(*, active_workspace: str, graph_storage: str) -> dict[str, Any]:
    """Combine rag_storage, Neo4j, and inputs views into one table."""
    return DEFAULT_WORKSPACE_MAINTENANCE.workspace_inventory(
        active_workspace=active_workspace,
        graph_storage=graph_storage,
    )


def delete_workspace_sync(
    name: str,
    scope: WorkspaceDeleteScope,
    *,
    graph_storage: str,
) -> dict[str, Any]:
    """Delete one workspace's selected storage buckets."""
    return DEFAULT_WORKSPACE_MAINTENANCE.delete_workspace(
        name,
        scope,
        graph_storage=graph_storage,
    )


def wipe_all_workspaces_sync(
    scope: WipeAllScope,
    *,
    active_workspace: str,
    graph_storage: str,
    inventory_func=workspace_inventory,
    delete_workspace_func=delete_workspace_sync,
    ensure_active_workspace=DEFAULT_WORKSPACE_MAINTENANCE.ensure_active_storage_workspace,
) -> dict[str, Any]:
    """Clean-slate wipe across every discovered workspace."""
    inventory = inventory_func(
        active_workspace=active_workspace,
        graph_storage=graph_storage,
    )
    names = [row["name"] for row in inventory["workspaces"]]
    results = [
        delete_workspace_func(
            name,
            WorkspaceDeleteScope(
                neo4j=scope.neo4j,
                rag_storage=scope.rag_storage,
                inputs=scope.inputs,
            ),
            graph_storage=graph_storage,
        )
        for name in names
    ]
    try:
        ensure_active_workspace(active_workspace)
    except Exception:  # noqa: BLE001
        pass
    return {"deleted": results, "workspaces": len(results)}


def ensure_active_storage_workspace(active_workspace: str) -> None:
    """Ensure the active rag_storage workspace exists after a clean-slate wipe."""
    DEFAULT_WORKSPACE_MAINTENANCE.ensure_active_storage_workspace(active_workspace)