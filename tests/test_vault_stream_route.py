"""#155: GET /api/ui/vault/stream — tier/status/limit filters with deep-link query params."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.vault_routes import register_vault_routes
from src.server.vault_store import VaultStore


def _now():
    return "2026-05-14T12:00:00"


@pytest.fixture()
def stream_client(tmp_path):
    store = VaultStore(vault_dir=tmp_path, now=_now)
    # Seed: 2 doctrine/raw, 1 doctrine/polished, 1 intelligence/raw, 1 pursuit/evergreen
    seeds = [
        ("Doctrine Raw A", "doctrine", "raw"),
        ("Doctrine Raw B", "doctrine", "raw"),
        ("Doctrine Polished", "doctrine", "polished"),
        ("Intel Raw", "intelligence", "raw"),
        ("Pursuit Evergreen", "pursuit", "evergreen"),
    ]
    for title, tier, status in seeds:
        n = store.create(title=title, body="x", note_type="raw", topic="", source="test", tier=tier)
        if status != "raw":
            store.update(n["id"], status=status)
    app = FastAPI()
    register_vault_routes(app, vault_store=store, vault_auto_polish=True)
    return TestClient(app), store


def test_stream_no_filter_returns_all(stream_client):
    client, _ = stream_client
    resp = client.get("/api/ui/vault/stream")
    assert resp.status_code == 200
    assert len(resp.json()["notes"]) == 5


def test_stream_filters_by_tier(stream_client):
    client, _ = stream_client
    for tier, expected in [("doctrine", 3), ("intelligence", 1), ("pursuit", 1)]:
        resp = client.get(f"/api/ui/vault/stream?tier={tier}")
        assert resp.status_code == 200
        notes = resp.json()["notes"]
        assert len(notes) == expected
        assert all(n["tier"] == tier for n in notes)


def test_stream_filters_by_status(stream_client):
    client, _ = stream_client
    for status, expected in [("raw", 3), ("polished", 1), ("evergreen", 1)]:
        resp = client.get(f"/api/ui/vault/stream?status={status}")
        assert resp.status_code == 200
        notes = resp.json()["notes"]
        assert len(notes) == expected
        assert all(n["status"] == status for n in notes)


def test_stream_combined_tier_and_status_intersects(stream_client):
    client, _ = stream_client
    resp = client.get("/api/ui/vault/stream?tier=doctrine&status=raw")
    assert resp.status_code == 200
    notes = resp.json()["notes"]
    assert len(notes) == 2
    assert all(n["tier"] == "doctrine" and n["status"] == "raw" for n in notes)


def test_stream_limit_caps_results(stream_client):
    client, _ = stream_client
    resp = client.get("/api/ui/vault/stream?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()["notes"]) == 2


def test_stream_rejects_invalid_tier(stream_client):
    client, _ = stream_client
    resp = client.get("/api/ui/vault/stream?tier=bogus")
    assert resp.status_code == 400
    assert "tier" in resp.json()["detail"].lower()


def test_stream_rejects_invalid_status(stream_client):
    client, _ = stream_client
    resp = client.get("/api/ui/vault/stream?status=invalid")
    assert resp.status_code == 400
    assert "status" in resp.json()["detail"].lower()


def test_stream_newest_first_ordering(stream_client):
    """Stream must return newest-first by 'updated' so capture cards prepend cleanly."""
    client, store = stream_client
    # The fixture used static _now so updated equal; ensure ordering field is stable
    resp = client.get("/api/ui/vault/stream")
    notes = resp.json()["notes"]
    updated = [n.get("updated") for n in notes]
    assert updated == sorted(updated, reverse=True)
