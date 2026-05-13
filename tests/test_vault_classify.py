"""Tests for AI background classification of vault notes.

Design: POST /api/ui/vault/notes saves the note as type='raw' with an empty/placeholder
title, then fires a FastAPI BackgroundTask that calls vault_curation_func, infers both
the real type AND a title, then PATCHes the note via store.update().

The TestClient runs background tasks synchronously before returning, so we can
assert the updated fields without polling.
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

def _make_app(tmp_path: Path, classify_response: str = "insight\nThis is a title"):
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
    """POST body-only note → background classify runs → type updated."""
    app, store = _make_app(tmp_path, classify_response="insight\nProven COTS Integration Win")

    with TestClient(app, raise_server_exceptions=True) as client:
        resp = client.post(
            "/api/ui/vault/notes",
            json={"body": "We have proven COTS integration", "type": "raw"},
        )
        assert resp.status_code == 201
        note_id = resp.json()["id"]

    # Background task ran; note type should be updated to "insight"
    updated = store.read(note_id)
    assert updated["type"] == "insight", f"Expected 'insight', got {updated['type']!r}"


def test_classify_action_type(tmp_path: Path) -> None:
    app, store = _make_app(tmp_path, classify_response="action\nCall the CO Tomorrow")

    with TestClient(app) as client:
        resp = client.post(
            "/api/ui/vault/notes",
            json={"body": "Call the CO tomorrow", "type": "raw"},
        )
        note_id = resp.json()["id"]

    updated = store.read(note_id)
    assert updated["type"] == "action"


def test_classify_ai_infers_title(tmp_path: Path) -> None:
    """Background classify must patch both type and title from LLM response."""
    app, store = _make_app(tmp_path, classify_response="insight\nProven COTS Integration Win")

    with TestClient(app) as client:
        resp = client.post(
            "/api/ui/vault/notes",
            json={"body": "We have proven COTS integration", "type": "raw"},
        )
        note_id = resp.json()["id"]

    updated = store.read(note_id)
    assert updated["title"] == "Proven COTS Integration Win"


def test_classify_invalid_llm_response_falls_back_to_raw(tmp_path: Path) -> None:
    """If LLM returns gibberish, type stays 'raw' (safe fallback)."""
    app, store = _make_app(tmp_path, classify_response="UNKNOWN_GOBBLEDYGOOK")

    with TestClient(app) as client:
        resp = client.post(
            "/api/ui/vault/notes",
            json={"body": "Not sure what this is", "type": "raw"},
        )
        note_id = resp.json()["id"]

    updated = store.read(note_id)
    assert updated["type"] == "raw", f"Invalid LLM output should fall back to 'raw', got {updated['type']!r}"


# ---------------------------------------------------------------------------
# Preview endpoint
# ---------------------------------------------------------------------------

def test_preview_endpoint_returns_title_type_body(tmp_path: Path) -> None:
    """POST /api/ui/vault/preview returns AI-polished title, type, and body."""
    app, _store = _make_app(
        tmp_path,
        classify_response="TYPE: insight\nTITLE: Proven COTS Integration Win\nBODY: We have proven COTS integration.",
    )
    with TestClient(app) as client:
        resp = client.post(
            "/api/ui/vault/preview",
            json={"body": "We have proven COTS integration"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "insight"
    assert data["title"] == "Proven COTS Integration Win"
    assert "integration" in data["body"].lower()


def test_preview_returns_503_without_curation_func(tmp_path: Path) -> None:
    """Preview endpoint returns 503 when no vault_curation_func is wired."""
    vault_dir = tmp_path / "knowledge"
    vault_dir.mkdir()
    from datetime import datetime, timezone
    store = VaultStore(vault_dir=vault_dir, now=lambda: datetime.now(timezone.utc).isoformat())
    app = FastAPI()
    register_vault_routes(app, vault_store=store)  # no func
    with TestClient(app) as client:
        resp = client.post("/api/ui/vault/preview", json={"body": "test"})
    assert resp.status_code == 503


def test_preview_fallback_on_malformed_response(tmp_path: Path) -> None:
    """When LLM returns gibberish for preview, type falls back to 'raw'."""
    app, _store = _make_app(tmp_path, classify_response="NOT_A_VALID_RESPONSE")
    with TestClient(app) as client:
        resp = client.post("/api/ui/vault/preview", json={"body": "some capture"})
    assert resp.status_code == 200
    assert resp.json()["type"] == "raw"


# ---------------------------------------------------------------------------
# No-curation-func guard
# ---------------------------------------------------------------------------

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
            json={"body": "No classifier wired", "type": "raw"},
        )
        note_id = resp.json()["id"]

    note = store.read(note_id)
    assert note["type"] == "raw"
