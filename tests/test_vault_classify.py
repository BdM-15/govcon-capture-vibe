"""Tests for AI background classification of vault notes.

Design: POST /api/ui/vault/notes saves the note as type='raw', then fires a
FastAPI BackgroundTask that calls vault_curation_func, infers the real type,
and PATCHes the note via store.update().

The TestClient runs background tasks synchronously before returning, so we can
assert the updated type without polling.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.vault_routes import register_vault_routes
from src.server.vault_store import VaultStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(tmp_path: Path, classify_response: str = "insight"):
    vault_dir = tmp_path / "knowledge"
    vault_dir.mkdir()
    from datetime import datetime, timezone
    store = VaultStore(vault_dir=vault_dir, now=lambda: datetime.now(timezone.utc).isoformat())

    async def mock_vault_curation(prompt, system_prompt=None, **kwargs):
        return classify_response

    app = FastAPI()
    register_vault_routes(app, vault_store=store, vault_curation_func=mock_vault_curation)
    return app, store


# ---------------------------------------------------------------------------
# Tracer bullet: classify fires and patches type
# ---------------------------------------------------------------------------

def test_create_note_triggers_background_classify(tmp_path: Path) -> None:
    """POST a note → background classify runs → type updated from 'raw' to inferred."""
    app, store = _make_app(tmp_path, classify_response="insight")

    with TestClient(app, raise_server_exceptions=True) as client:
        resp = client.post(
            "/api/ui/vault/notes",
            json={"title": "Win theme idea", "body": "We have proven COTS integration", "type": "raw"},
        )
        assert resp.status_code == 201
        note_id = resp.json()["id"]

    # Background task ran; note type should be updated to "insight"
    updated = store.read(note_id)
    assert updated["type"] == "insight", f"Expected 'insight', got {updated['type']!r}"


def test_classify_action_type(tmp_path: Path) -> None:
    app, store = _make_app(tmp_path, classify_response="action")

    with TestClient(app) as client:
        resp = client.post(
            "/api/ui/vault/notes",
            json={"title": "Follow-up item", "body": "Call the CO tomorrow", "type": "raw"},
        )
        note_id = resp.json()["id"]

    updated = store.read(note_id)
    assert updated["type"] == "action"


def test_classify_invalid_llm_response_falls_back_to_raw(tmp_path: Path) -> None:
    """If LLM returns gibberish, type stays 'raw' (safe fallback)."""
    app, store = _make_app(tmp_path, classify_response="UNKNOWN_GOBBLEDYGOOK")

    with TestClient(app) as client:
        resp = client.post(
            "/api/ui/vault/notes",
            json={"title": "Ambiguous note", "body": "Not sure what this is", "type": "raw"},
        )
        note_id = resp.json()["id"]

    updated = store.read(note_id)
    assert updated["type"] == "raw", f"Invalid LLM output should fall back to 'raw', got {updated['type']!r}"


def test_no_vault_curation_func_leaves_type_as_submitted(tmp_path: Path) -> None:
    """When no vault_curation_func is wired, no background classify fires; type unchanged."""
    vault_dir = tmp_path / "knowledge"
    vault_dir.mkdir()
    from datetime import datetime, timezone
    store = VaultStore(vault_dir=vault_dir, now=lambda: datetime.now(timezone.utc).isoformat())

    app = FastAPI()
    register_vault_routes(app, vault_store=store)  # no vault_curation_func

    with TestClient(app) as client:
        resp = client.post(
            "/api/ui/vault/notes",
            json={"title": "Orphan note", "body": "No classifier wired", "type": "raw"},
        )
        note_id = resp.json()["id"]

    note = store.read(note_id)
    assert note["type"] == "raw"
