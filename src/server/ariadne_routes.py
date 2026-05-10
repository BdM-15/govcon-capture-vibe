"""Ariadne's Thread API routes."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from src.core.ariadne_fit import FORMULA_VERSION, fit_scores
from src.core.global_store import GlobalStore
from src.server.workspace_routes import discover_workspaces, workspace_inventory


def _promotion_map(
    *,
    store: GlobalStore,
    workspace_names: list[str],
    workspace_root: Path,
) -> dict[str, list[dict[str, Any]]]:
    promotions: dict[str, list[dict[str, Any]]] = {}
    for name in workspace_names:
        try:
            promotions[name] = store.list_promotions(
                workspace=name,
                workspace_root=workspace_root,
                active_only=True,
            )
        except ValueError:
            promotions[name] = []
    return promotions


def register_ariadne_fit_routes(
    app: FastAPI,
    *,
    workspace_name: Callable[[], str],
    working_dir: Callable[[], Path],
    graph_storage: Callable[[], str],
    store_factory: Callable[[], GlobalStore] | None = None,
    discover_func: Callable[[Path], list[dict[str, Any]]] = discover_workspaces,
    inventory_func: Callable[..., dict[str, Any]] = workspace_inventory,
) -> None:
    """Register deterministic Ariadne scoring endpoints."""
    if store_factory is None:
        store_factory = GlobalStore

    @app.get("/api/ariadne/fit-scores", tags=["theseus-ui"])
    async def ariadne_fit_scores(
        limit: int = Query(default=20, ge=1, le=100),
    ) -> JSONResponse:
        active_workspace = workspace_name()
        workspace_root = working_dir()
        workspaces = discover_func(workspace_root)
        inventory_payload = await asyncio.to_thread(
            inventory_func,
            active_workspace=active_workspace,
            graph_storage=graph_storage(),
        )
        inventory = inventory_payload.get("workspaces") or []
        names = sorted(
            {
                str(row.get("name") or "")
                for row in [*workspaces, *inventory]
                if row.get("name")
            }
        )
        store = store_factory()
        promotions = await asyncio.to_thread(
            _promotion_map,
            store=store,
            workspace_names=names,
            workspace_root=workspace_root,
        )
        wiki_count = len(store.list("llm-wiki"))
        scores = fit_scores(
            workspaces=workspaces,
            inventory=inventory,
            promotions_by_workspace=promotions,
            wiki_count=wiki_count,
            active_workspace=active_workspace,
            limit=limit,
        )
        return JSONResponse(
            {
                "active": active_workspace,
                "formula_version": FORMULA_VERSION,
                "scores": scores,
            }
        )


__all__ = ["register_ariadne_fit_routes"]