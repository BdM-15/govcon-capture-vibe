import json
from pathlib import Path
from types import SimpleNamespace
import subprocess

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.ontology.schema import VALID_ENTITY_TYPES, VALID_RELATIONSHIP_TYPES
from src.server import admin_routes as dashboard_stats
from src.server.admin_routes import (
    gather_stats,
    register_dashboard_stats_routes,
    release_version,
    ui_chat_history_pairs,
)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        workspace="demo",
        extraction_llm_name="extract-model",
        reasoning_llm_name="reason-model",
        embedding_model="embed-model",
        rerank_model="rerank-model",
        enable_rerank=True,
    )


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_ui_chat_history_pairs_uses_env_with_safe_fallback(monkeypatch) -> None:
    monkeypatch.setenv("UI_CHAT_HISTORY_TURNS", "7")
    assert ui_chat_history_pairs() == 7

    monkeypatch.setenv("UI_CHAT_HISTORY_TURNS", "-2")
    assert ui_chat_history_pairs() == 0

    monkeypatch.setenv("UI_CHAT_HISTORY_TURNS", "not-a-number")
    assert ui_chat_history_pairs() == 20


def test_gather_stats_counts_workspace_and_shapes_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("UI_CHAT_HISTORY_TURNS", "3")
    workspace = tmp_path / "demo"
    chats = workspace / "chats"
    chats.mkdir(parents=True)
    _write_json(workspace / "kv_store_doc_status.json", {"doc-a": {}, "doc-b": {}})
    _write_json(workspace / "vdb_entities.json", {"data": [{}, {}, {}]})
    _write_json(workspace / "vdb_relationships.json", {"r1": {}, "r2": {}})
    _write_json(workspace / "vdb_chunks.json", [{}, {}, {}, {}])
    (chats / "chat.json").write_text("{}", encoding="utf-8")

    payload = gather_stats(
        workspace_dir=lambda: workspace,
        chats_dir=lambda: chats,
        settings_provider=_settings,
        graph_storage=lambda: "Neo4JStorage",
        now=lambda: "2026-05-03T12:00:00-05:00",
        stack_versions_func=lambda: {"lightrag": "test"},
        release_version_func=lambda: "v1.4.0",
    )

    assert payload["workspace"] == "demo"
    assert payload["graph_storage"] == "Neo4JStorage"
    assert payload["documents"] == 2
    assert payload["entities"] == 3
    assert payload["relationships"] == 2
    assert payload["chunks"] == 4
    assert payload["chats"] == 1
    assert payload["chat"] == {"history_pairs_cap": 3}
    assert payload["version"] == "v1.4.0"
    assert payload["ontology"]["entity_type_count"] == len(VALID_ENTITY_TYPES)
    assert payload["ontology"]["relationship_type_count"] == len(VALID_RELATIONSHIP_TYPES)
    assert payload["models"]["rerank"] == "rerank-model"
    assert payload["stack"] == {"lightrag": "test"}
    assert payload["timestamp"] == "2026-05-03T12:00:00-05:00"


def test_dashboard_stats_route_uses_injected_dependencies(tmp_path) -> None:
    app = FastAPI()
    workspace = tmp_path / "demo"
    chats = workspace / "chats"
    chats.mkdir(parents=True)
    register_dashboard_stats_routes(
        app,
        workspace_dir=lambda: workspace,
        chats_dir=lambda: chats,
        settings_provider=_settings,
        graph_storage=lambda: "NetworkXStorage",
        now=lambda: "now",
    )
    client = TestClient(app)

    response = client.get("/api/ui/stats")

    assert response.status_code == 200, response.text
    assert response.json()["workspace"] == "demo"
    assert response.json()["graph_storage"] == "NetworkXStorage"


def test_release_version_uses_repo_root_for_git_tag(monkeypatch) -> None:
    monkeypatch.delenv("THESEUS_RELEASE_VERSION", raising=False)
    monkeypatch.setattr(dashboard_stats, "_RELEASE_VERSION_CACHE", None)
    captured: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        captured["cwd"] = kwargs["cwd"]
        return SimpleNamespace(stdout="v1.4.0\n")

    monkeypatch.setattr(dashboard_stats.subprocess, "run", fake_run)

    assert release_version() == "v1.4.0"
    assert captured["cwd"] == Path(dashboard_stats.__file__).resolve().parents[2]


def test_release_version_does_not_cache_fallback(monkeypatch) -> None:
    monkeypatch.delenv("THESEUS_RELEASE_VERSION", raising=False)
    monkeypatch.setattr(dashboard_stats, "_RELEASE_VERSION_CACHE", None)
    calls = {"count": 0}

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(dashboard_stats.subprocess, "run", fake_run)

    assert release_version() == "v0.0.0"
    assert dashboard_stats._RELEASE_VERSION_CACHE is None
    assert release_version() == "v0.0.0"
    assert calls["count"] == 2
