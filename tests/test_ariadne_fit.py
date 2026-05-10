from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.ariadne_fit import FORMULA_VERSION, fit_scores
from src.core.global_store import GlobalStore
from src.server.ariadne_routes import register_ariadne_fit_routes


def _note(body: str) -> str:
    return (
        "---\n"
        "date: 2026-05-10\n"
        "source: capture\n"
        "status: evergreen\n"
        "tags: [capability]\n"
        "---\n\n"
        f"{body}\n"
    )


def test_fit_scores_derive_component_breakdown() -> None:
    scores = fit_scores(
        workspaces=[{"name": "demo", "documents": 1, "entities": 50}],
        inventory=[
            {
                "name": "demo",
                "neo4j_nodes": 12,
                "pursuit": {
                    "stage": "capture",
                    "gate": {"due": "2026-05-31"},
                    "pwin": {"value": 62},
                    "pwin_drivers": [{"key": "solution"}],
                },
            }
        ],
        promotions_by_workspace={
            "demo": [
                {"ingestion_status": "processed"},
                {"ingestion_status": "pending"},
            ]
        },
        wiki_count=1,
        active_workspace="demo",
    )

    score = scores[0]

    assert score["formula_version"] == FORMULA_VERSION
    assert score["workspace"] == "demo"
    assert score["score"] == 75
    assert score["accent"] == "lime"
    assert score["stage"] == "capture"
    assert score["is_active_workspace"] is True
    assert score["detail"] == "KG, source, wiki, metadata ready"
    assert score["components"] == [
        {"key": "kg", "label": "KG", "value": 42, "max": 45},
        {"key": "sources", "label": "Sources", "value": 13, "max": 30},
        {"key": "wiki", "label": "Wiki", "value": 10, "max": 15},
        {"key": "meta", "label": "Meta", "value": 10, "max": 10},
    ]
    assert score["source_counts"]["promoted_processed"] == 1
    assert score["source_counts"]["promoted_pending"] == 1


def test_ariadne_fit_scores_route_uses_global_store_manifest(tmp_path: Path) -> None:
    app = FastAPI()
    store = GlobalStore(root=tmp_path / "global")
    workspace_root = tmp_path / "rag_storage"
    store.write("llm-wiki/capability.md", _note("Capability proof point"))
    store.write("notes/source.md", _note("Promoted source"))
    store.promote(
        "notes/source.md",
        workspace="demo",
        workspace_root=workspace_root,
    )
    store.update_promotion_ingestion(
        "notes/source.md",
        workspace="demo",
        workspace_root=workspace_root,
        ingestion_status="processed",
        doc_id="doc-demo",
    )

    def inventory_func(*, active_workspace: str, graph_storage: str) -> dict[str, Any]:
        return {
            "active": active_workspace,
            "neo4j_available": graph_storage == "Neo4JStorage",
            "workspaces": [
                {
                    "name": "demo",
                    "is_active": True,
                    "neo4j_nodes": 12,
                    "pursuit": {
                        "stage": "capture",
                        "gate": {"due": "2026-05-31"},
                        "pwin": {"value": 62},
                        "pwin_drivers": [{"key": "solution"}],
                    },
                }
            ],
        }

    register_ariadne_fit_routes(
        app,
        workspace_name=lambda: "demo",
        working_dir=lambda: workspace_root,
        graph_storage=lambda: "Neo4JStorage",
        store_factory=lambda: store,
        discover_func=lambda _root: [
            {"name": "demo", "documents": 1, "entities": 50, "chats": 0}
        ],
        inventory_func=inventory_func,
    )
    client = TestClient(app)

    response = client.get("/api/ariadne/fit-scores")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active"] == "demo"
    assert body["formula_version"] == FORMULA_VERSION
    assert body["scores"][0]["workspace"] == "demo"
    assert body["scores"][0]["score"] == 72
    assert body["scores"][0]["source_counts"]["promoted_processed"] == 1
    assert body["scores"][0]["source_counts"]["llm_wiki"] == 1