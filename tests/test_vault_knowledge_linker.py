"""Tests for #144 — Knowledge Linker: workspace-aware vault recommendation panel."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.vault_routes import register_vault_routes
from src.server.vault_store import VaultStore

_ISO_NOW = "2026-05-13T00:00:00Z"


def _now() -> str:
    return _ISO_NOW

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ENTITY_MAP: dict[str, list[str]] = {
    "rfp_test": ["cloud migration", "zero trust security", "CMMC compliance", "DevSecOps pipeline"],
    "empty_workspace": [],
}


async def _entities_func(workspace: str) -> list[str]:
    return _ENTITY_MAP.get(workspace, [])


@pytest.fixture
def store(tmp_path):
    return VaultStore(vault_dir=tmp_path, now=_now)


@pytest.fixture
def app_with_store(store):
    app = FastAPI()
    register_vault_routes(app, vault_store=store, entities_func=_entities_func)
    return TestClient(app), store


@pytest.fixture
def client_with_notes(app_with_store):
    client, store = app_with_store
    store.create(
        title="Cloud Migration Plan",
        body="We should migrate to cloud using zero trust security principles.",
        note_type="insight",
        topic="cloud",
        source="manual",
    )
    store.create(
        title="Lunch menu",
        body="Pizza Friday this week. Completely unrelated.",
        note_type="raw",
        topic="",
        source="manual",
    )
    store.create(
        title="CMMC readiness",
        body="Our CMMC compliance gap analysis is complete. DevSecOps pipeline is ready for audit.",
        note_type="insight",
        topic="compliance",
        source="manual",
    )
    store.create(
        title="PM meeting",
        body="Met with PM to discuss schedule.",
        note_type="raw",
        topic="",
        source="manual",
    )
    return client, store


# ---------------------------------------------------------------------------
# Backend: recommend endpoint
# ---------------------------------------------------------------------------


class TestRecommendEndpoint:
    def test_recommend_no_workspace_returns_empty(self, client_with_notes):
        client, _ = client_with_notes
        r = client.get("/api/ui/vault/recommend")
        assert r.status_code == 200
        data = r.json()
        assert data["recommendations"] == []

    def test_recommend_with_workspace_returns_sorted_list(self, client_with_notes):
        client, _ = client_with_notes
        r = client.get("/api/ui/vault/recommend?workspace=rfp_test")
        assert r.status_code == 200
        recs = r.json()["recommendations"]
        assert len(recs) > 0
        # CMMC + DevSecOps note should rank high
        titles = [rec["title"] for rec in recs]
        assert any("CMMC" in t or "Cloud" in t for t in titles)
        # Scores descending
        scores = [rec["score"] for rec in recs]
        assert scores == sorted(scores, reverse=True)

    def test_recommend_limit_respected(self, client_with_notes):
        client, _ = client_with_notes
        r = client.get("/api/ui/vault/recommend?workspace=rfp_test&limit=1")
        assert r.status_code == 200
        assert len(r.json()["recommendations"]) <= 1

    def test_recommend_response_shape(self, client_with_notes):
        client, _ = client_with_notes
        r = client.get("/api/ui/vault/recommend?workspace=rfp_test")
        assert r.status_code == 200
        recs = r.json()["recommendations"]
        assert len(recs) > 0
        first = recs[0]
        for field in ("id", "title", "type", "status", "excerpt", "score"):
            assert field in first, f"Missing field: {field}"
        assert isinstance(first["score"], (int, float))
        assert isinstance(first["excerpt"], str)

    def test_recommend_empty_vault_returns_empty(self, app_with_store):
        client, _ = app_with_store
        r = client.get("/api/ui/vault/recommend?workspace=rfp_test")
        assert r.status_code == 200
        assert r.json()["recommendations"] == []

    def test_recommend_no_entity_match_returns_empty(self, client_with_notes):
        client, _ = client_with_notes
        r = client.get("/api/ui/vault/recommend?workspace=empty_workspace")
        assert r.status_code == 200
        assert r.json()["recommendations"] == []

    def test_recommend_no_entities_func_uses_empty(self, store):
        """Without entities_func, all workspaces return empty recommendations."""
        store.create(
            title="Cloud Plan", body="cloud migration", note_type="raw", topic="", source="manual"
        )
        app = FastAPI()
        register_vault_routes(app, vault_store=store)
        client = TestClient(app)
        r = client.get("/api/ui/vault/recommend?workspace=rfp_test")
        assert r.status_code == 200
        assert r.json()["recommendations"] == []


# ---------------------------------------------------------------------------
# Backend: feed-to-workspace endpoint
# ---------------------------------------------------------------------------


class TestFeedToWorkspace:
    def test_feed_sets_pursuit_field(self, client_with_notes):
        client, store = client_with_notes
        note_id = store.list_notes()[0]["id"]
        r = client.post(
            f"/api/ui/vault/notes/{note_id}/feed",
            json={"workspace": "rfp_test"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["pursuit"] == "rfp_test"

    def test_feed_nonexistent_returns_404(self, app_with_store):
        client, _ = app_with_store
        r = client.post("/api/ui/vault/notes/no-such-id/feed", json={"workspace": "rfp_test"})
        assert r.status_code == 404

    def test_feed_response_shape(self, client_with_notes):
        client, store = client_with_notes
        note_id = store.list_notes()[0]["id"]
        r = client.post(
            f"/api/ui/vault/notes/{note_id}/feed",
            json={"workspace": "rfp_test"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert "title" in data
        assert data["pursuit"] == "rfp_test"


# ---------------------------------------------------------------------------
# Frontend: state vars
# ---------------------------------------------------------------------------


class TestVaultLinkerState:
    def test_vault_recommend_state_vars_present(self):
        state_path = Path("src/ui/static/app/theseus-state-helpers.js")
        src = state_path.read_text(encoding="utf-8")
        assert "vaultRecommendations" in src
        assert "vaultRecommendLoading" in src


# ---------------------------------------------------------------------------
# Frontend: helpers
# ---------------------------------------------------------------------------


class TestVaultLinkerHelpers:
    def test_vault_recommend_helpers_exported(self):
        helpers_path = Path("src/ui/static/app/theseus-vault-helpers.js")
        src = helpers_path.read_text(encoding="utf-8")
        assert "theseusVaultLoadRecommendations" in src
        assert "theseusVaultFeedToWorkspace" in src


# ---------------------------------------------------------------------------
# Frontend: delegates
# ---------------------------------------------------------------------------


class TestVaultLinkerDelegates:
    def test_vault_recommend_delegates_wired(self):
        delegates_path = Path("src/ui/static/app/theseus-app-delegates.js")
        src = delegates_path.read_text(encoding="utf-8")
        assert "vaultLoadRecommendations" in src
        assert "vaultFeedToWorkspace" in src


# ---------------------------------------------------------------------------
# Frontend: HTML panel
# ---------------------------------------------------------------------------


class TestVaultLinkerHtml:
    def test_relevant_vault_section_in_right_pane(self):
        html = Path("src/ui/static/index.html").read_text(encoding="utf-8")
        assert "Relevant in your vault" in html

    def test_feed_to_workspace_button_in_html(self):
        html = Path("src/ui/static/index.html").read_text(encoding="utf-8")
        assert "vaultFeedToWorkspace" in html

    def test_vault_recommendations_loop_in_html(self):
        html = Path("src/ui/static/index.html").read_text(encoding="utf-8")
        assert "vaultRecommendations" in html
