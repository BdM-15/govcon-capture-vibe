"""Workspace admin models and pure operations used by the UI routes."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.core import reset_settings
from src.server.storage_counts import safe_count_json_keys

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
    if not working_dir.exists():
        return []
    signature_files = ("kv_store_doc_status.json", "vdb_entities.json", "vdb_chunks.json")
    workspaces: list[dict[str, Any]] = []
    for child in sorted(working_dir.iterdir()):
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        has_data = any((child / filename).exists() for filename in signature_files)
        workspaces.append(
            {
                "name": child.name,
                "has_data": has_data,
                "documents": safe_count_json_keys(child / "kv_store_doc_status.json"),
                "entities": safe_count_json_keys(child / "vdb_entities.json"),
                "chats": sum(1 for _ in (child / "chats").glob("*.json")) if (child / "chats").exists() else 0,
            }
        )
    return workspaces


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
    from tools.workspace_cleanup import (
        _inputs_root,
        _inputs_workspaces,
        _neo4j_workspaces,
        _rag_storage_root,
        _storage_workspaces,
    )

    rag_root = _rag_storage_root()
    inputs_root = _inputs_root()
    storage_ws = _storage_workspaces(rag_root)
    inputs_ws = _inputs_workspaces(inputs_root)

    neo4j_ws: dict[str, int] = {}
    backend = (graph_storage or "").lower()
    if "neo4j" in backend:
        try:
            from src.inference.neo4j_graph_io import Neo4jGraphIO

            io = Neo4jGraphIO()
            try:
                neo4j_ws = _neo4j_workspaces(io)
            finally:
                io.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Neo4j inventory failed: %s", exc)

    all_names = sorted(set(neo4j_ws) | set(storage_ws) | set(inputs_ws))
    rows: list[dict[str, Any]] = []
    for name in all_names:
        inputs = inputs_ws.get(name)
        rows.append(
            {
                "name": name,
                "is_active": name == active_workspace,
                "neo4j_nodes": neo4j_ws.get(name, 0),
                "storage_mb": storage_ws.get(name),
                "inputs_files": inputs[0] if inputs else 0,
                "inputs_mb": inputs[1] if inputs else 0.0,
            }
        )
    return {
        "active": active_workspace,
        "rag_storage_root": str(rag_root),
        "inputs_root": str(inputs_root),
        "neo4j_available": "neo4j" in backend,
        "workspaces": rows,
    }


def delete_workspace_sync(
    name: str,
    scope: WorkspaceDeleteScope,
    *,
    graph_storage: str,
) -> dict[str, Any]:
    """Delete one workspace's selected storage buckets."""
    from tools.workspace_cleanup import (
        _delete_inputs_workspace,
        _delete_neo4j_workspace,
        _delete_storage_workspace,
        _inputs_root,
        _rag_storage_root,
    )

    result: dict[str, Any] = {"workspace": name, "deleted": {}}

    if scope.neo4j:
        backend = (graph_storage or "").lower()
        if "neo4j" in backend:
            try:
                from src.inference.neo4j_graph_io import Neo4jGraphIO

                io = Neo4jGraphIO()
                try:
                    nodes = _delete_neo4j_workspace(io, name)
                    result["deleted"]["neo4j_nodes"] = nodes
                finally:
                    io.close()
            except Exception as exc:  # noqa: BLE001
                result["deleted"]["neo4j_error"] = str(exc)
        else:
            result["deleted"]["neo4j_skipped"] = "backend is not Neo4j"

    if scope.rag_storage:
        try:
            existed = _delete_storage_workspace(name, _rag_storage_root())
            result["deleted"]["rag_storage"] = existed
        except Exception as exc:  # noqa: BLE001
            result["deleted"]["rag_storage_error"] = str(exc)

    if scope.inputs:
        try:
            count, mb = _delete_inputs_workspace(name, _inputs_root())
            workspace_inputs = _inputs_root() / name
            if workspace_inputs.exists() and workspace_inputs.is_dir() and not any(workspace_inputs.iterdir()):
                try:
                    workspace_inputs.rmdir()
                except OSError:
                    pass
            result["deleted"]["inputs_files"] = count
            result["deleted"]["inputs_mb"] = mb
        except Exception as exc:  # noqa: BLE001
            result["deleted"]["inputs_error"] = str(exc)

    return result


def ensure_active_storage_workspace(active_workspace: str) -> None:
    """Ensure the active rag_storage workspace exists after a clean-slate wipe."""
    from tools.workspace_cleanup import _rag_storage_root

    (_rag_storage_root() / active_workspace).mkdir(parents=True, exist_ok=True)