"""Dashboard stats route and rollup helpers for the Theseus UI."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.core import get_settings
from src.core.env import env_int
from src.ontology.schema import VALID_ENTITY_TYPES, VALID_RELATIONSHIP_TYPES
from src.server.storage_counts import safe_count_json_keys
from src.utils.time_utils import now_local_iso

_STACK_CACHE: Optional[dict[str, Optional[str]]] = None
_RELEASE_VERSION_CACHE: Optional[str] = None
_REPO_ROOT = Path(__file__).resolve().parents[2]


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
