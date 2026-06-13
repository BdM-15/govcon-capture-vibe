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
from src.server.runtime_state import (
    clear_langgraph_studio_status,
    clear_ollama_status,
    set_langgraph_studio_status,
    set_ollama_status,
)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        workspace="demo",
        extraction_llm_name="extract-model",
        reasoning_llm_name="reason-model",
        keyword_llm_name="grok-4.20-0309-non-reasoning",

        embedding_model="embed-model",
        vlm_llm_name="vlm-model",
        rerank_model="rerank-model",
        enable_rerank=True,
        ollama_host="http://localhost:11434",
        ollama_model="qwen3.5:9b",
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
    assert payload["storage"] == {
        "graph": "Neo4JStorage",
        "vector": "NanoVectorDBStorage",
        "kv": "JsonKVStorage",
        "doc_status": "JsonDocStatusStorage",
    }
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
    assert payload["models"]["vlm"] == "vlm-model"
    assert payload["models"]["keyword"] == "grok-4.20-0309-non-reasoning"
    assert payload["ollama"]["model"] == "qwen3.5:9b"
    assert payload["ollama"]["state"] == "unknown"
    assert payload["stack"] == {"lightrag": "test"}
    assert payload["timestamp"] == "2026-05-03T12:00:00-05:00"


def test_gather_stats_includes_langgraph_studio_status(tmp_path) -> None:
    workspace = tmp_path / "demo"
    chats = workspace / "chats"
    chats.mkdir(parents=True)
    set_langgraph_studio_status(
        {
            "ok": True,
            "state": "ready",
            "url": "http://127.0.0.1:2024",
            "graph_url": "https://smith.langchain.com/studio/?baseUrl=http%3A//127.0.0.1%3A2024&graph=mission_readiness",
            "version": "1.2.5",
            "started_by_us": True,
        }
    )
    try:
        payload = gather_stats(
            workspace_dir=lambda: workspace,
            chats_dir=lambda: chats,
            settings_provider=_settings,
        )
    finally:
        clear_langgraph_studio_status()

    assert payload["langgraph_studio"]["ok"] is True
    assert payload["langgraph_studio"]["state"] == "ready"
    assert "mission_readiness" in payload["langgraph_studio"]["graph_url"]


def test_gather_stats_includes_ollama_warmup_status(tmp_path) -> None:
    workspace = tmp_path / "demo"
    chats = workspace / "chats"
    chats.mkdir(parents=True)
    set_ollama_status(
        {
            "ok": True,
            "state": "ready",
            "model": "qwen3.5:9b",
            "host": "http://localhost:11434",
            "available": ["qwen3.5:9b"],
            "warmed_at": "2026-06-10T12:00:00",

        }
    )
    try:
        payload = gather_stats(
            workspace_dir=lambda: workspace,
            chats_dir=lambda: chats,
            settings_provider=_settings,
        )
    finally:
        clear_ollama_status()

    assert payload["ollama"]["ready"] is True
    assert payload["ollama"]["state"] == "ready"
    assert payload["ollama"]["warmed_at"] == "2026-06-10T12:00:00"


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
        vector_storage=lambda: "NanoVectorDBStorage",
        kv_storage=lambda: "JsonKVStorage",
        now=lambda: "now",
    )
    client = TestClient(app)

    response = client.get("/api/ui/stats")

    assert response.status_code == 200, response.text
    assert response.json()["workspace"] == "demo"
    assert response.json()["graph_storage"] == "NetworkXStorage"
    assert response.json()["storage"]["vector"] == "NanoVectorDBStorage"


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
