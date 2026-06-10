import json
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.chat_routes import (
    DEFAULT_RESPONSE_TYPE,
    QuerySettingsStore,
    register_query_settings_routes,
)


@dataclass
class FakeSettings:
    workspace: str = "demo"
    enable_rerank: bool = True
    min_rerank_score: float = 0.42


def _store(tmp_path: Path, settings: FakeSettings | None = None) -> QuerySettingsStore:
    workspace = tmp_path / "demo"
    workspace.mkdir(exist_ok=True)
    active_settings = settings or FakeSettings()
    return QuerySettingsStore(
        workspace_dir=lambda: workspace,
        settings_provider=lambda: active_settings,
    )


def test_query_settings_store_defaults_use_env_and_settings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TOP_K", "17")
    monkeypatch.setenv("CHUNK_TOP_K", "8")
    store = _store(tmp_path, FakeSettings(enable_rerank=False, min_rerank_score=0.2))

    defaults = store.defaults()

    assert defaults["mode"] == "mix"
    assert defaults["top_k"] == 17
    assert defaults["chunk_top_k"] == 8
    assert defaults["enable_rerank"] is False
    assert defaults["min_rerank_score"] == 0.2
    assert defaults["response_type"] == DEFAULT_RESPONSE_TYPE


def test_query_settings_store_defaults_fallback_for_invalid_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TOP_K", "not-a-number")
    monkeypatch.setenv("CHUNK_TOP_K", "9999")
    store = _store(tmp_path)

    defaults = store.defaults()

    assert defaults["top_k"] == 40
    assert defaults["chunk_top_k"] == 500


def test_query_settings_store_merges_known_overrides_only(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.path().write_text(
        json.dumps({"top_k": 5, "stream": False, "ignored": "x"}),
        encoding="utf-8",
    )

    settings = store.read()

    assert settings["top_k"] == 5
    assert settings["stream"] is False
    assert "ignored" not in settings


def test_query_settings_store_builds_query_overrides(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write({**store.defaults(), "mode": "local", "stream": False, "top_k": 3})

    overrides = store.build_overrides()

    assert overrides["top_k"] == 3
    assert overrides["min_rerank_score"] == 0.42
    assert overrides["response_type"] == DEFAULT_RESPONSE_TYPE
    assert "mode" not in overrides
    assert "stream" not in overrides


def test_query_settings_store_honors_ui_max_total_tokens(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.write({**store.defaults(), "max_total_tokens": 200_000})

    assert store.read()["max_total_tokens"] == 200_000
    assert store.build_overrides()["max_total_tokens"] == 200_000


def test_query_settings_routes_update_and_reset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TOP_K", "40")
    store = _store(tmp_path)
    app = FastAPI()
    register_query_settings_routes(
        app,
        workspace_name=lambda: "demo",
        store=store,
    )
    client = TestClient(app)

    response = client.put("/api/ui/settings/query", json={"mode": "hybrid", "top_k": 11})
    assert response.status_code == 200, response.text
    assert response.json()["settings"]["top_k"] == 11
    assert json.loads(store.path().read_text(encoding="utf-8"))["mode"] == "hybrid"

    bad = client.put("/api/ui/settings/query", json={"mode": "weird"})
    assert bad.status_code == 400

    reset = client.post("/api/ui/settings/query/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["settings"]["top_k"] == 40
    assert not store.path().exists()
