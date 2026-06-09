"""
Custom Project Theseus UI routes.

Mounts a single-page cyberpunk capture-management UI at /ui and exposes a
small set of JSON endpoints under /api/ui/* for things the upstream
LightRAG WebUI does not provide:

- Dashboard rollups
- File-based chat persistence (one JSON file per chat,
  rag_storage/<workspace>/chats/<chat_id>.json)
- Shipley phase 4-6 suggested-prompt library

All RAG/graph/document data continues to flow through the upstream
LightRAG endpoints (`/query`, `/graphs`, `/documents`, etc.) plus our
custom `/insert`, `/documents/upload`, and `/scan-rfp`. This module
intentionally adds zero new Python dependencies.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Union

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from lightrag.api.config import global_args

# query_func signature: (text, mode, history, stream, overrides) -> str | AsyncIterator[str]
# - history: list of {"role": "user"|"assistant", "content": str}
# - overrides: dict of QueryParam tunables (top_k, chunk_top_k, max_*_tokens,
#   enable_rerank, only_need_context, only_need_prompt, response_type, user_prompt)
#   plus an optional "min_rerank_score" applied to the LightRAG instance for the call.
# - stream=False returns awaitable str; stream=True returns awaitable AsyncIterator[str]
QueryFunc = Callable[
    [str, str, list[dict], bool, dict],
    Awaitable[Union[str, AsyncIterator[str]]],
]

# data_func signature: (text, mode, history, overrides) -> dict
# Returns LightRAG aquery_data shape: {status, message, data: {chunks, entities, relationships, references}}.
QueryDataFunc = Callable[
    [str, str, list[dict], dict],
    Awaitable[dict],
]


class TheseusStaticFiles(StaticFiles):
    """StaticFiles variant that disables browser caching for live UI edits."""

    def file_response(self, *args, **kwargs):  # type: ignore[override]
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

from src.core import get_settings
from src.server.chat_store import ChatStore
from src.server.chat_routes import (
    QuerySettingsStore,
    register_chat_routes,
    register_query_settings_routes,
)
from src.server.admin_routes import (
    register_dashboard_stats_routes,
    register_mcp_ui_routes,
    ui_chat_history_pairs,
)
from src.server.document_routes import register_processing_log_routes
from src.server.prompt_library import register_prompt_library_routes
from src.server.skill_routes import register_skill_ui_routes
from src.server.entity_chunk_routes import register_entity_chunk_routes
from src.server.graph_routes import register_graph_routes
from src.server.intelligence_routes import register_intelligence_routes
from src.server.workspace_maintenance import self_restart as _self_restart, set_env_var as _set_env_var
from src.server.workspace_ui_routes import register_workspace_ui_routes

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent
_STATIC_DIR = (_THIS_DIR.parent / "ui" / "static").resolve()


def _workspace_dir() -> Path:
    """Return the active workspace directory under rag_storage/."""
    settings = get_settings()
    return Path(global_args.working_dir) / settings.workspace


def _chats_dir() -> Path:
    """Return (and create) the chats persistence directory for this workspace."""
    folder = _workspace_dir() / "chats"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from src.utils.time_utils import now_local_iso as _now_local_iso


def _now_iso() -> str:
    """ISO timestamp in America/Chicago (CST/CDT)."""
    return _now_local_iso(timespec="seconds")


@dataclass
class UIRouteContext:
    """Shared closures and stores consumed by UI route registration."""

    workspace_dir: Callable[[], Path]
    chats_dir: Callable[[], Path]
    workspace_name: Callable[[], str]
    graph_storage: Callable[[], str]
    vector_storage: Callable[[], str]
    kv_storage: Callable[[], str]
    working_dir: Callable[[], Path]
    now: Callable[[], str]
    set_env_var: Callable[[str, str], None]
    schedule_restart: Callable[[float], None]
    query_settings: Any
    chat_store: Any


def build_ui_route_context(
    *,
    workspace_dir: Callable[[], Path],
    chats_dir: Callable[[], Path],
    now: Callable[[], str],
    settings_provider: Callable[[], Any],
    history_pairs: Callable[[], int],
    global_args_obj: Any,
    set_env_var_func: Callable[[str, str], None],
    restart_func: Callable[[], None],
    query_settings_cls=QuerySettingsStore,
    chat_store_cls=ChatStore,
    call_later: Callable[[float, Callable[[], None]], None] | None = None,
) -> UIRouteContext:
    """Construct the shared stores and closures used across UI route modules."""
    if call_later is None:
        call_later = lambda delay, fn: asyncio.get_event_loop().call_later(delay, fn)

    query_settings = query_settings_cls(
        workspace_dir=workspace_dir,
        settings_provider=settings_provider,
    )
    chat_store = chat_store_cls(
        workspace_dir=workspace_dir,
        now=now,
        history_pairs=history_pairs,
    )

    return UIRouteContext(
        workspace_dir=workspace_dir,
        chats_dir=chats_dir,
        workspace_name=lambda: settings_provider().workspace,
        graph_storage=lambda: getattr(global_args_obj, "graph_storage", "") or "",
        vector_storage=lambda: getattr(global_args_obj, "vector_storage", "NanoVectorDBStorage") or "NanoVectorDBStorage",
        kv_storage=lambda: getattr(global_args_obj, "kv_storage", "JsonKVStorage") or "JsonKVStorage",
        working_dir=lambda: Path(global_args_obj.working_dir),
        now=now,
        set_env_var=lambda key, value: set_env_var_func(key, value),
        schedule_restart=lambda delay: call_later(delay, restart_func),
        query_settings=query_settings,
        chat_store=chat_store,
    )


def _register_feature_routes(
    app: FastAPI,
    *,
    context: UIRouteContext,
    query_func: QueryFunc,
    data_func: QueryDataFunc | None,
    llm_func: "LlmFunc" | None,
) -> None:
    """Register all feature-owner route modules behind the UI shell."""
    register_dashboard_stats_routes(
        app,
        workspace_dir=context.workspace_dir,
        chats_dir=context.chats_dir,
        settings_provider=get_settings,
        graph_storage=context.graph_storage,
        vector_storage=context.vector_storage,
        kv_storage=context.kv_storage,
        now=context.now,
    )

    register_processing_log_routes(app)
    register_prompt_library_routes(app)

    register_chat_routes(
        app,
        chat_store=context.chat_store,
        query_settings=context.query_settings,
        query_func=query_func,
        data_func=data_func,
        now=context.now,
    )

    register_entity_chunk_routes(app, workspace_dir=context.workspace_dir)
    register_intelligence_routes(app, workspace_dir=context.workspace_dir)

    register_graph_routes(
        app,
        workspace_name=context.workspace_name,
        graph_storage=context.graph_storage,
        working_dir=context.working_dir,
    )

    register_workspace_ui_routes(
        app,
        workspace_name=context.workspace_name,
        working_dir=context.working_dir,
        graph_storage=context.graph_storage,
        set_env_var_func=context.set_env_var,
        schedule_restart=context.schedule_restart,
    )

    register_query_settings_routes(
        app,
        workspace_name=context.workspace_name,
        store=context.query_settings,
    )

    register_skill_ui_routes(
        app,
        workspace_dir=context.workspace_dir,
        data_func=data_func,
        llm_func=llm_func,
        set_env_var=context.set_env_var,
    )

    register_mcp_ui_routes(
        app,
        set_env_var=context.set_env_var,
        schedule_restart=context.schedule_restart,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

LlmFunc = Callable[[str], Awaitable[str]]


def register_ui(
    app: FastAPI,
    query_func: QueryFunc,
    data_func: QueryDataFunc | None = None,
    llm_func: LlmFunc | None = None,
) -> None:
    """
    Register the Project Theseus UI routes on an existing FastAPI app.

    Args:
        app: The FastAPI app produced by lightrag.api.lightrag_server.create_app.
        query_func: Async callable (query_text, mode, history, stream, overrides)
                    -> str | AsyncIterator[str]. The conversation_history is a
                    list of {role, content} dicts; when stream=True the return
                    is an async iterator of token chunks.
        data_func: Optional async callable (query_text, mode, history, overrides)
                    -> dict that returns LightRAG aquery_data structured retrieval
                    (chunks/entities/relationships/references). Used by the chat
                    SSE endpoint to emit a `sources` event before streaming the
                    answer. If None, no sources event is emitted.
    """
    if not _STATIC_DIR.exists():
        logger.warning("UI static dir missing: %s — UI will not be mounted", _STATIC_DIR)
        return

    context = build_ui_route_context(
        workspace_dir=_workspace_dir,
        chats_dir=_chats_dir,
        now=_now_iso,
        settings_provider=get_settings,
        history_pairs=ui_chat_history_pairs,
        global_args_obj=global_args,
        set_env_var_func=lambda key, value: _set_env_var(key, value),
        restart_func=lambda: _self_restart(),
    )

    # ---- Fragmented SPA shell assembled at serve time (#190) ---------------
    from src.ui.workbench_assembler import assemble_workbench_html

    def _workbench_html() -> str:
        return assemble_workbench_html(str(_STATIC_DIR))

    @app.get("/ui", include_in_schema=False)
    @app.get("/ui/", include_in_schema=False)
    @app.get("/ui/index.html", include_in_schema=False)
    async def serve_workbench_shell() -> HTMLResponse:
        return HTMLResponse(
            _workbench_html(),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    # ---- Static assets under /ui (app/, styles/, views/ for dev only) ----
    app.mount(
        "/ui",
        TheseusStaticFiles(directory=str(_STATIC_DIR), html=True),
        name="theseus-ui",
    )

    _register_feature_routes(
        app,
        context=context,
        query_func=query_func,
        data_func=data_func,
        llm_func=llm_func,
    )

    logger.info("✅ Project Theseus UI mounted at /ui (static: %s)", _STATIC_DIR)
