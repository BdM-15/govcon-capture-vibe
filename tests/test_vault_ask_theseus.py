"""TDD contract tests for Vault Ask Theseus → Save as Note (#143).

Backend:
  - POST /api/ui/vault/notes/{id}/ask-theseus with workspace query_func → mode=workspace_kg
  - POST /api/ui/vault/notes/{id}/ask-theseus without query_func → mode=vault_only
  - POST /api/ui/vault/notes/{id}/ask-theseus on non-existent note → 404
  - Response shape: {answer, sources, mode}

Save as Note:
  - POST /api/ui/vault/notes/{id}/ask-theseus/save creates insight note with correct frontmatter

State:
  - vaultAskAnswer, vaultAskLoading, vaultAskSources present in Alpine initial state

Vault helpers:
  - theseusVaultAskTheseus exported from theseus-vault-helpers.js
  - theseusVaultSaveAsNote exported from theseus-vault-helpers.js

App delegates:
  - vaultAskTheseus wired in theseus-app-delegates.js
  - vaultSaveAsNote wired in theseus-app-delegates.js

HTML:
  - Ask Theseus button present in right pane
  - Answer display area in right pane
  - Save as Note button in right pane
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

_ROOT = Path(__file__).parent.parent
_STATE = _ROOT / "src" / "ui" / "static" / "app" / "theseus-state-helpers.js"
_VAULT_HELPERS = _ROOT / "src" / "ui" / "static" / "app" / "theseus-vault-helpers.js"
_DELEGATES = _ROOT / "src" / "ui" / "static" / "app" / "theseus-app-delegates.js"
_INDEX = _ROOT / "src" / "ui" / "static" / "index.html"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_now = lambda: datetime.now(timezone.utc).isoformat()


@pytest.fixture()
def vault_store(tmp_path):
    from src.server.vault_store import VaultStore
    return VaultStore(vault_dir=tmp_path, now=_now)


@pytest.fixture()
def vault_client_no_query(tmp_path):
    """TestClient with NO query_func — vault-only mode."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.server.vault_routes import register_vault_routes
    from src.server.vault_store import VaultStore

    store = VaultStore(vault_dir=tmp_path, now=_now)
    app = FastAPI()
    register_vault_routes(app, vault_store=store)
    return TestClient(app), store


@pytest.fixture()
def vault_client_with_query(tmp_path):
    """TestClient with a mock query_func — workspace_kg mode."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.server.vault_routes import register_vault_routes
    from src.server.vault_store import VaultStore

    store = VaultStore(vault_dir=tmp_path, now=_now)
    mock_query = AsyncMock(return_value="Mock Shipley answer from workspace KG.")
    app = FastAPI()
    register_vault_routes(app, vault_store=store, query_func=mock_query)
    return TestClient(app), store, mock_query


# ---------------------------------------------------------------------------
# Backend: ask-theseus route — vault_only fallback
# ---------------------------------------------------------------------------

def test_ask_theseus_vault_only_mode(vault_client_no_query):
    """Without query_func, returns mode=vault_only and an answer."""
    client, store = vault_client_no_query
    note = store.create(title="Test Note", body="What are the key risks?", note_type="raw", topic="", source="manual")
    resp = client.post(f"/api/ui/vault/notes/{note['id']}/ask-theseus")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "vault_only"
    assert "answer" in data
    assert isinstance(data["sources"], list)


def test_ask_theseus_workspace_kg_mode(vault_client_with_query):
    """With query_func, returns mode=workspace_kg and calls the mock."""
    client, store, mock_query = vault_client_with_query
    note = store.create(title="Test Note", body="Summarize the RFP requirements.", note_type="raw", topic="", source="manual")
    resp = client.post(
        f"/api/ui/vault/notes/{note['id']}/ask-theseus",
        json={"workspace": "test_ws"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "workspace_kg"
    assert "answer" in data
    assert len(data["answer"]) > 0


def test_ask_theseus_nonexistent_returns_404(vault_client_no_query):
    """Non-existent note → 404."""
    client, _ = vault_client_no_query
    resp = client.post("/api/ui/vault/notes/nonexistent-id/ask-theseus")
    assert resp.status_code == 404


def test_ask_theseus_response_shape(vault_client_no_query):
    """Response always has answer, sources, mode keys."""
    client, store = vault_client_no_query
    note = store.create(title="Shape test", body="Some content here.", note_type="raw", topic="", source="manual")
    resp = client.post(f"/api/ui/vault/notes/{note['id']}/ask-theseus")
    data = resp.json()
    assert set(data.keys()) >= {"answer", "sources", "mode"}


# ---------------------------------------------------------------------------
# Backend: save-as-note route
# ---------------------------------------------------------------------------

def test_save_as_note_creates_insight(vault_client_no_query):
    """POST /ask-theseus/save creates a note with type=insight, source=ask_theseus."""
    client, store = vault_client_no_query
    note = store.create(title="Source Note", body="Original content.", note_type="raw", topic="", source="manual")
    resp = client.post(
        f"/api/ui/vault/notes/{note['id']}/ask-theseus/save",
        json={"answer": "The key risk is X.", "source_title": "Source Note"},
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["type"] == "insight"
    assert created["source"] == "ask_theseus"
    assert created["status"] == "raw"


def test_save_as_note_linked_from_set(vault_client_no_query):
    """Saved insight note has linked_from referencing the original note title."""
    client, store = vault_client_no_query
    note = store.create(title="My RFP Analysis", body="Details here.", note_type="raw", topic="", source="manual")
    resp = client.post(
        f"/api/ui/vault/notes/{note['id']}/ask-theseus/save",
        json={"answer": "Answer text here.", "source_title": "My RFP Analysis"},
    )
    assert resp.status_code == 201
    created = resp.json()
    assert "[[My RFP Analysis]]" in created.get("body", "")


def test_save_as_note_nonexistent_parent_returns_404(vault_client_no_query):
    """POST /ask-theseus/save on missing parent → 404."""
    client, _ = vault_client_no_query
    resp = client.post(
        "/api/ui/vault/notes/ghost-note/ask-theseus/save",
        json={"answer": "Whatever.", "source_title": "Ghost"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# State vars
# ---------------------------------------------------------------------------

def test_vault_ask_state_vars_present():
    """vaultAskAnswer, vaultAskLoading, vaultAskSources in Alpine state."""
    text = _STATE.read_text(encoding="utf-8")
    assert "vaultAskAnswer" in text
    assert "vaultAskLoading" in text
    assert "vaultAskSources" in text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
