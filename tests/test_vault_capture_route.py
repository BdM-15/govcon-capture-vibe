"""B2: Tests for POST /api/ui/vault/capture route.

The route wraps `vault_capture.capture(...)` and exposes it over HTTP.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.vault_routes import register_vault_routes
from src.server.vault_store import VaultStore


def _now():
    return "2026-05-14T12:00:00"


@pytest.fixture()
def vault_capture_client(tmp_path):
    store = VaultStore(vault_dir=tmp_path, now=_now)
    fake_llm = AsyncMock(return_value=(
        "TYPE: insight\n"
        "TITLE: Competitor X wins cleared workforce IDIQ\n"
        "BODY: Competitor X recently won a [[Cleared Workforce]] IDIQ."
    ))
    app = FastAPI()
    register_vault_routes(
        app,
        vault_store=store,
        vault_curation_func=fake_llm,
        vault_auto_polish=True,
    )
    return TestClient(app), store, fake_llm


def test_capture_route_happy_path_returns_classified_polished_note(vault_capture_client):
    client, store, fake_llm = vault_capture_client

    resp = client.post(
        "/api/ui/vault/capture",
        json={"body": "competitor X just won an idiq for cleared workforce work"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["note_type"] == "insight"
    assert data["title"] == "Competitor X wins cleared workforce IDIQ"
    assert data["auto_polished"] is True
    assert "Competitor X" in data["polished_body"]
    assert isinstance(data["wikilink_suggestions"], list)  # empty vault -> empty list
    assert data["note_id"]
    fake_llm.assert_awaited_once()

    # Persisted and listable
    listed = store.list_notes()
    assert len(listed) == 1
    assert listed[0]["id"] == data["note_id"]
    assert listed[0]["type"] == "insight"


def test_capture_route_rejects_empty_body(vault_capture_client):
    client, store, fake_llm = vault_capture_client

    resp = client.post("/api/ui/vault/capture", json={"body": "   "})
    assert resp.status_code == 400
    assert "empty" in resp.text.lower()
    fake_llm.assert_not_awaited()
    assert store.list_notes() == []


def test_capture_route_503_when_polish_requested_without_llm(tmp_path):
    """auto_polish=True but no vault_curation_func configured -> 503."""
    store = VaultStore(vault_dir=tmp_path, now=_now)
    app = FastAPI()
    register_vault_routes(app, vault_store=store, vault_auto_polish=True)
    client = TestClient(app)

    resp = client.post("/api/ui/vault/capture", json={"body": "valid body"})
    assert resp.status_code == 503
    assert "not configured" in resp.text.lower()
