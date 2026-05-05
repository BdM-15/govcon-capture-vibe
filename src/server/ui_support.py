"""Shared dependency/context builders for the Theseus UI route layer."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.server.chat_store import ChatStore
from src.server.query_settings import QuerySettingsStore


@dataclass
class UIRouteContext:
    """Shared closures and stores consumed by UI route registration."""

    workspace_dir: Callable[[], Path]
    chats_dir: Callable[[], Path]
    workspace_name: Callable[[], str]
    graph_storage: Callable[[], str]
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
        working_dir=lambda: Path(global_args_obj.working_dir),
        now=now,
        set_env_var=lambda key, value: set_env_var_func(key, value),
        schedule_restart=lambda delay: call_later(delay, restart_func),
        query_settings=query_settings,
        chat_store=chat_store,
    )