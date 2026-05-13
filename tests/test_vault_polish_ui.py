"""TDD contract tests for vault note polish (slice 5).

Backend:
- polish_note endpoint loads note, calls curation LLM, updates store, returns note
- returns 503 when Ollama is down (existing _require_ollama gate)

Frontend:
- theseusPolishVaultNote helper defined in vault-helpers
- polishVaultNote delegate in app-delegates
- Polish button on note cards
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_ROOT = Path(__file__).parent.parent
_VAULT_HELPERS = _ROOT / "src" / "ui" / "static" / "app" / "theseus-vault-helpers.js"
_APP_DELEGATES = _ROOT / "src" / "ui" / "static" / "app" / "theseus-app-delegates.js"
_INDEX = _ROOT / "src" / "ui" / "static" / "index.html"


# ── backend ───────────────────────────────────────────────────────────────────

def test_polish_endpoint_not_stub() -> None:
    """polish_note must not return 501 not_implemented."""
    from src.server.vault_routes import register_vault_routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    store = MagicMock()
    store.read.return_value = {
        "id": "test-note", "title": "Old title", "body": "raw dump",
        "type": "raw", "status": "raw", "updated": "2026-01-01T00:00:00Z",
    }
    store.update.return_value = {
        "id": "test-note", "title": "Polished title", "body": "clean body",
        "type": "insight", "status": "polished", "updated": "2026-01-02T00:00:00Z",
    }
    store.list_notes.return_value = []

    curation_mock = AsyncMock(return_value="TYPE: insight\nTITLE: Polished title\nBODY: clean body")

    # Patch _ollama_available so _require_ollama passes
    import src.server.vault_routes as vr
    orig = vr._ollama_available
    vr._ollama_available = True
    try:
        app = FastAPI()
        register_vault_routes(app, vault_store=store, vault_curation_func=curation_mock)
        client = TestClient(app)
        resp = client.post("/api/ui/vault/notes/test-note/polish")
        assert resp.status_code != 501, "polish_note must not return 501 (stub not implemented)"
    finally:
        vr._ollama_available = orig


def test_polish_endpoint_calls_curation_and_updates_store() -> None:
    """polish_note must call vault_curation_func and vault_store.update."""
    from src.server.vault_routes import register_vault_routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    store = MagicMock()
    store.read.return_value = {
        "id": "note-1", "title": "Old", "body": "raw body text",
        "type": "raw", "status": "raw", "updated": "2026-01-01T00:00:00Z",
    }
    store.update.return_value = {
        "id": "note-1", "title": "Clean title", "body": "polished",
        "type": "insight", "status": "polished", "updated": "2026-01-02T00:00:00Z",
    }
    store.list_notes.return_value = []

    curation_mock = AsyncMock(return_value="TYPE: insight\nTITLE: Clean title\nBODY: polished")

    import src.server.vault_routes as vr
    orig = vr._ollama_available
    vr._ollama_available = True
    try:
        app = FastAPI()
        register_vault_routes(app, vault_store=store, vault_curation_func=curation_mock)
        client = TestClient(app)
        resp = client.post("/api/ui/vault/notes/note-1/polish", json={"model": "qwen", "accept": True})
        assert resp.status_code == 200
        curation_mock.assert_awaited_once()
        store.update.assert_called_once()
        # status must be set to polished
        call_kwargs = store.update.call_args
        assert call_kwargs[1].get("status") == "polished" or (
            len(call_kwargs[0]) > 1 and "polished" in str(call_kwargs)
        ), "vault_store.update must set status='polished'"
    finally:
        vr._ollama_available = orig


def test_polish_endpoint_503_when_ollama_down() -> None:
    """polish_note must 503 when Ollama is not available."""
    from src.server.vault_routes import register_vault_routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    store = MagicMock()
    curation_mock = AsyncMock()

    import src.server.vault_routes as vr
    orig = vr._ollama_available
    vr._ollama_available = False
    try:
        app = FastAPI()
        register_vault_routes(app, vault_store=store, vault_curation_func=curation_mock)
        client = TestClient(app)
        resp = client.post("/api/ui/vault/notes/any-note/polish")
        assert resp.status_code == 503
    finally:
        vr._ollama_available = orig


# ── frontend ──────────────────────────────────────────────────────────────────

def test_polish_helper_defined_in_vault_helpers() -> None:
    """theseusPolishVaultNote must be defined in theseus-vault-helpers.js."""
    js = _VAULT_HELPERS.read_text(encoding="utf-8")
    assert "theseusPolishVaultNote" in js


def test_polish_helper_posts_to_polish_endpoint() -> None:
    """theseusPolishVaultNote must POST to .../polish."""
    js = _VAULT_HELPERS.read_text(encoding="utf-8")
    idx = js.find("theseusPolishVaultNote")
    assert idx != -1
    body = js[idx:]
    assert "/polish" in body


def test_polish_delegate_defined() -> None:
    """polishVaultNote must exist in app-delegates."""
    js = _APP_DELEGATES.read_text(encoding="utf-8")
    assert "polishVaultNote" in js


def test_note_card_has_polish_button() -> None:
    """Each note card must have a polish action button."""
    html = _INDEX.read_text(encoding="utf-8")
    assert "polishVaultNote" in html
