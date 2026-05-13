"""TDD contract tests for Vault right pane + Promote (#142).

Backend:
  - POST /api/ui/vault/notes/{id}/promote advances raw→polished→evergreen
  - POST /api/ui/vault/notes/{id}/promote on evergreen is idempotent

State:
  - vaultRightPaneOpen present in Alpine initial state

Vault helpers:
  - theseusVaultPromoteNote exported from theseus-vault-helpers.js

App delegates:
  - vaultPromoteNote wired in theseus-app-delegates.js

HTML:
  - right pane container present inside the vault notes tab layout
  - promote button with vaultPromoteNote call present in right pane
  - note metadata (source, tags, created) visible in right pane
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

import pytest

_ROOT = Path(__file__).parent.parent
_STATE = _ROOT / "src" / "ui" / "static" / "app" / "theseus-state-helpers.js"
_VAULT_HELPERS = _ROOT / "src" / "ui" / "static" / "app" / "theseus-vault-helpers.js"
_DELEGATES = _ROOT / "src" / "ui" / "static" / "app" / "theseus-app-delegates.js"
_INDEX = _ROOT / "src" / "ui" / "static" / "index.html"


# ---------------------------------------------------------------------------
# Fixtures
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
    app = FastAPI()
    register_vault_routes(app, vault_store=store)
    return TestClient(app), store


# ---------------------------------------------------------------------------
# Backend: promote route
# ---------------------------------------------------------------------------

def test_promote_raw_to_polished(vault_client):
    """POST /promote on a raw note sets status to polished."""
    client, store = vault_client
    note = store.create(title="Raw note", body="body", note_type="raw", topic="t", source="s")
    assert note["status"] == "raw"

    resp = client.post(f"/api/ui/vault/notes/{note['id']}/promote")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "polished"
    assert data["id"] == note["id"]


def test_promote_polished_to_evergreen(vault_client):
    """POST /promote on a polished note sets status to evergreen."""
    client, store = vault_client
    note = store.create(title="Polished note", body="body", note_type="insight", topic="t", source="s")
    store.update(note["id"], status="polished")

    resp = client.post(f"/api/ui/vault/notes/{note['id']}/promote")
    assert resp.status_code == 200
    assert resp.json()["status"] == "evergreen"


def test_promote_evergreen_is_idempotent(vault_client):
    """POST /promote on an evergreen note keeps it evergreen."""
    client, store = vault_client
    note = store.create(title="Evergreen note", body="body", note_type="insight", topic="t", source="s")
    store.update(note["id"], status="evergreen")

    resp = client.post(f"/api/ui/vault/notes/{note['id']}/promote")
    assert resp.status_code == 200
    assert resp.json()["status"] == "evergreen"


def test_promote_nonexistent_returns_404(vault_client):
    """POST /promote on a missing note returns 404."""
    client, _ = vault_client
    resp = client.post("/api/ui/vault/notes/no-such-note/promote")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# State: vaultRightPaneOpen
# ---------------------------------------------------------------------------

def test_vault_right_pane_open_state_var():
    """vaultRightPaneOpen must be present in Alpine initial state."""
    js = _STATE.read_text(encoding="utf-8")
    assert "vaultRightPaneOpen" in js, "vaultRightPaneOpen missing from theseus-state-helpers.js"


# ---------------------------------------------------------------------------
# Vault helpers: theseusVaultPromoteNote
# ---------------------------------------------------------------------------

def test_vault_promote_helper_exported():
    """theseusVaultPromoteNote must be window-exported in theseus-vault-helpers.js."""
    js = _VAULT_HELPERS.read_text(encoding="utf-8")
    assert "window.theseusVaultPromoteNote" in js, (
        "theseusVaultPromoteNote not found in theseus-vault-helpers.js"
    )


# ---------------------------------------------------------------------------
# App delegates: vaultPromoteNote
# ---------------------------------------------------------------------------

def test_vault_promote_delegate_wired():
    """vaultPromoteNote() delegate must be present in theseus-app-delegates.js."""
    js = _DELEGATES.read_text(encoding="utf-8")
    assert "vaultPromoteNote" in js, "vaultPromoteNote missing from theseus-app-delegates.js"
    assert "theseusVaultPromoteNote" in js, (
        "vaultPromoteNote delegate must call theseusVaultPromoteNote"
    )


# ---------------------------------------------------------------------------
# HTML: right pane structure
# ---------------------------------------------------------------------------

def test_vault_right_pane_container_in_html():
    """Notes tab HTML must contain a right-pane container alongside left/center."""
    html = _INDEX.read_text(encoding="utf-8")
    assert "vault-right-pane" in html, (
        "Right pane container (vault-right-pane id/class) missing from index.html"
    )


def test_vault_promote_button_in_html():
    """Right pane must have a promote button wired to vaultPromoteNote."""
    html = _INDEX.read_text(encoding="utf-8")
    assert "vaultPromoteNote" in html, (
        "vaultPromoteNote call missing from index.html promote button"
    )


def test_vault_right_pane_shows_metadata():
    """Right pane must display note source and created date."""
    html = _INDEX.read_text(encoding="utf-8")
    assert "vaultActiveNote.source" in html, "source field missing from right pane"
    assert "vaultActiveNote.created" in html, "created field missing from right pane"


def test_vault_right_pane_toggle_button_in_html():
    """A toggle button for the right pane must be present."""
    html = _INDEX.read_text(encoding="utf-8")
    assert "vaultRightPaneOpen" in html, (
        "vaultRightPaneOpen toggle not found in index.html"
    )
