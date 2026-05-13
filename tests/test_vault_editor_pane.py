"""TDD contract tests for Vault left + center panes (#141).

Backend:
  - GET /api/ui/vault/notes?q=term filters by title/body
  - GET /api/ui/vault/notes?type=insight filters by type
  - GET /api/ui/vault/notes?status=polished filters by status

State:
  - vaultActiveNote, vaultEditorMode, vaultSearch,
    vaultFilterType, vaultFilterStatus, vaultFilterTopic, vaultFilterPursuit
    all present in Alpine initial state

Vault helpers:
  - theseusVaultSelectNote, theseusVaultNewNote, theseusVaultSaveNote exported

HTML:
  - left-pane search input bound to vaultSearch
  - filter dropdown for type, status
  - "New Note" button calls vaultNewNote
  - editor toolbar has Editor / Preview / Mind Map toggles
  - center pane has title input for active note
  - markmap CDN script present
  - Preview toggle renders via marked (uses vaultEditorMode === 'preview')
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

import pytest

_ROOT = Path(__file__).parent.parent
_STATE = _ROOT / "src" / "ui" / "static" / "app" / "theseus-state-helpers.js"
_VAULT_HELPERS = _ROOT / "src" / "ui" / "static" / "app" / "theseus-vault-helpers.js"
_INDEX = _ROOT / "src" / "ui" / "static" / "index.html"


# ---------------------------------------------------------------------------
# Backend: search + filter route
# ---------------------------------------------------------------------------

@pytest.fixture()
def vault_client(tmp_path):
    """FastAPI TestClient with vault routes mounted over a temp vault dir."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.server.vault_routes import register_vault_routes
    from src.server.vault_store import VaultStore

    _now = lambda: datetime.now(timezone.utc).isoformat()
    store = VaultStore(vault_dir=tmp_path, now=_now)

    # Seed some notes
    store.create(title="Alpha insight", body="body alpha", note_type="insight", topic="capture", source="test")
    store.create(title="Beta risk", body="contains beta keyword", note_type="risk", topic="pricing", source="test")
    n = store.create(title="Gamma polished", body="polished note", note_type="insight", topic="capture", source="test")
    store.update(n["id"], status="polished")

    app = FastAPI()
    register_vault_routes(app, vault_store=store)
    return TestClient(app)


def test_vault_notes_no_filter_returns_all(vault_client):
    resp = vault_client.get("/api/ui/vault/notes")
    assert resp.status_code == 200
    notes = resp.json()["notes"]
    assert len(notes) == 3


def test_vault_notes_search_q_filters_by_title(vault_client):
    resp = vault_client.get("/api/ui/vault/notes?q=alpha")
    assert resp.status_code == 200
    notes = resp.json()["notes"]
    assert len(notes) == 1
    assert notes[0]["title"] == "Alpha insight"


def test_vault_notes_search_q_filters_by_body(vault_client):
    resp = vault_client.get("/api/ui/vault/notes?q=beta keyword")
    assert resp.status_code == 200
    notes = resp.json()["notes"]
    assert len(notes) == 1
    assert notes[0]["title"] == "Beta risk"


def test_vault_notes_filter_by_type(vault_client):
    resp = vault_client.get("/api/ui/vault/notes?type=risk")
    assert resp.status_code == 200
    notes = resp.json()["notes"]
    assert len(notes) == 1
    assert notes[0]["type"] == "risk"


def test_vault_notes_filter_type_insight_returns_two(vault_client):
    resp = vault_client.get("/api/ui/vault/notes?type=insight")
    assert resp.status_code == 200
    notes = resp.json()["notes"]
    assert len(notes) == 2


def test_vault_notes_filter_by_status(vault_client):
    resp = vault_client.get("/api/ui/vault/notes?status=polished")
    assert resp.status_code == 200
    notes = resp.json()["notes"]
    assert len(notes) == 1
    assert notes[0]["title"] == "Gamma polished"


# ---------------------------------------------------------------------------
# State: new Alpine variables
# ---------------------------------------------------------------------------

def test_state_has_vault_active_note():
    js = _STATE.read_text(encoding="utf-8")
    assert "vaultActiveNote:" in js, "vaultActiveNote missing from Alpine state"


def test_state_has_vault_editor_mode():
    js = _STATE.read_text(encoding="utf-8")
    assert "vaultEditorMode:" in js, "vaultEditorMode missing from Alpine state"


def test_state_has_vault_search():
    js = _STATE.read_text(encoding="utf-8")
    assert "vaultSearch:" in js, "vaultSearch missing from Alpine state"


def test_state_has_vault_filter_type():
    js = _STATE.read_text(encoding="utf-8")
    assert "vaultFilterType:" in js, "vaultFilterType missing from Alpine state"


def test_state_has_vault_filter_status():
    js = _STATE.read_text(encoding="utf-8")
    assert "vaultFilterStatus:" in js, "vaultFilterStatus missing from Alpine state"


# ---------------------------------------------------------------------------
# Vault helpers: required functions exported
# ---------------------------------------------------------------------------

def test_vault_helpers_has_select_note():
    js = _VAULT_HELPERS.read_text(encoding="utf-8")
    assert "theseusVaultSelectNote" in js, "theseusVaultSelectNote missing from vault helpers"


def test_vault_helpers_has_new_note():
    js = _VAULT_HELPERS.read_text(encoding="utf-8")
    assert "theseusVaultNewNote" in js, "theseusVaultNewNote missing from vault helpers"


def test_vault_helpers_has_save_note():
    js = _VAULT_HELPERS.read_text(encoding="utf-8")
    assert "theseusVaultSaveNote" in js, "theseusVaultSaveNote missing from vault helpers"


# ---------------------------------------------------------------------------
# HTML: left pane
# ---------------------------------------------------------------------------

def test_html_has_vault_search_input():
    html = _INDEX.read_text(encoding="utf-8")
    assert 'x-model="vaultSearch"' in html, "left pane search input missing x-model='vaultSearch'"


def test_html_has_vault_filter_type_dropdown():
    html = _INDEX.read_text(encoding="utf-8")
    assert 'x-model="vaultFilterType"' in html, "type filter dropdown missing x-model='vaultFilterType'"


def test_html_has_new_note_button():
    html = _INDEX.read_text(encoding="utf-8")
    assert "vaultNewNote" in html, "New Note button must call vaultNewNote"


# ---------------------------------------------------------------------------
# HTML: center pane editor
# ---------------------------------------------------------------------------

def test_html_has_editor_toolbar_modes():
    html = _INDEX.read_text(encoding="utf-8")
    assert "vaultEditorMode" in html, "center pane must have editor mode toggle referencing vaultEditorMode"
    # Check at least editor and preview mode references
    assert "'editor'" in html or '"editor"' in html, "editor mode missing"
    assert "'preview'" in html or '"preview"' in html, "preview mode missing"


def test_html_has_active_note_title_input():
    html = _INDEX.read_text(encoding="utf-8")
    assert "vaultActiveNote.title" in html, "center pane must have editable title input for active note"


def test_html_has_active_note_body_textarea():
    html = _INDEX.read_text(encoding="utf-8")
    assert "vaultActiveNote.body" in html, "center pane must bind body textarea to vaultActiveNote.body"


def test_html_has_markmap_cdn():
    html = _INDEX.read_text(encoding="utf-8")
    assert "markmap" in html, "markmap CDN script must be loaded for Mind Map mode"
