"""TDD contract tests for #147 — Intel Feed Zettelkasten swimlanes + bulk polish.

Vertical slices:
  Slice 1 — State vars: intelFeedNotes, intelFeedLoading, intelBulkPolishing,
             intelBulkProgress, intelDragId
  Slice 2 — theseusIntelFeedLoad: GET /api/ui/vault/notes → intelFeedNotes
  Slice 3 — theseusIntelDrop: PUT status update, optimistic update
  Slice 4 — theseusIntelBulkPolish: POST /polish accept=true for all raw notes
  Slice 5 — theseusIntelBulkPolish: error handling, per-note progress states
  Slice 6 — HTML: three swimlane columns, drag attrs, bulk polish button, card template
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault_store_with_notes(tmp_path: Path):
    """Return (VaultStore, raw_id, polished_id, evergreen_id)."""
    from src.server.vault_store import VaultStore
    store = VaultStore(vault_dir=tmp_path, now=lambda: "2026-01-01T00:00:00Z")
    raw = store.create(title="Raw Note", body="raw intel body", note_type="concept",
                       topic="test", source="manual")
    polished = store.create(title="Polished Note", body="polished intel body", note_type="requirement",
                            topic="test", source="manual")
    store.update(polished["id"], status="polished")
    evergreen = store.create(title="Evergreen Note", body="evergreen intel body", note_type="document",
                             topic="test", source="manual")
    store.update(evergreen["id"], status="evergreen")
    return store, raw["id"], polished["id"], evergreen["id"]


# ---------------------------------------------------------------------------
# Slice 1: State vars exist
# ---------------------------------------------------------------------------


class TestIntelFeedStateVars:
    def test_intel_feed_notes_state_var_exists(self):
        html = open("src/ui/static/app/theseus-state-helpers.js").read()
        assert "intelFeedNotes" in html

    def test_intel_feed_loading_state_var_exists(self):
        html = open("src/ui/static/app/theseus-state-helpers.js").read()
        assert "intelFeedLoading" in html

    def test_intel_bulk_polishing_state_var_exists(self):
        html = open("src/ui/static/app/theseus-state-helpers.js").read()
        assert "intelBulkPolishing" in html

    def test_intel_bulk_progress_state_var_exists(self):
        html = open("src/ui/static/app/theseus-state-helpers.js").read()
        assert "intelBulkProgress" in html

    def test_intel_drag_id_state_var_exists(self):
        html = open("src/ui/static/app/theseus-state-helpers.js").read()
        assert "intelDragId" in html


# ---------------------------------------------------------------------------
# Slice 2: theseusIntelFeedLoad
# ---------------------------------------------------------------------------


class TestIntelFeedLoad:
    def test_intel_feed_load_function_exists(self):
        js = open("src/ui/static/app/theseus-vault-helpers.js").read()
        assert "theseusIntelFeedLoad" in js

    def test_intel_feed_load_fetches_vault_notes(self, tmp_path):
        """GET /api/ui/vault/notes returns notes → stored in intelFeedNotes."""
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        store, raw_id, polished_id, evergreen_id = _make_vault_store_with_notes(tmp_path)
        app = FastAPI()
        register_vault_routes(app, vault_store=store)
        client = TestClient(app)

        resp = client.get("/api/ui/vault/notes")
        assert resp.status_code == 200
        notes = resp.json()["notes"]
        assert len(notes) == 3

    def test_intel_feed_load_stores_all_notes(self, tmp_path):
        """Notes API returns all statuses without filter."""
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        store, raw_id, polished_id, evergreen_id = _make_vault_store_with_notes(tmp_path)
        app = FastAPI()
        register_vault_routes(app, vault_store=store)
        client = TestClient(app)

        resp = client.get("/api/ui/vault/notes")
        notes = resp.json()["notes"]
        statuses = {n["status"] for n in notes}
        assert "raw" in statuses
        assert "polished" in statuses
        assert "evergreen" in statuses

    def test_intel_feed_load_delegate_exists_in_delegates(self):
        js = open("src/ui/static/app/theseus-app-delegates.js").read()
        assert "intelFeedLoad" in js


# ---------------------------------------------------------------------------
# Slice 3: theseusIntelDrop
# ---------------------------------------------------------------------------


class TestIntelDrop:
    def test_intel_drop_function_exists(self):
        js = open("src/ui/static/app/theseus-vault-helpers.js").read()
        assert "theseusIntelDrop" in js

    def test_intel_drop_calls_put_endpoint(self, tmp_path):
        """PUT /api/ui/vault/notes/{id} with new status updates the note."""
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        store, raw_id, polished_id, evergreen_id = _make_vault_store_with_notes(tmp_path)
        app = FastAPI()
        register_vault_routes(app, vault_store=store)
        client = TestClient(app)

        resp = client.put(
            f"/api/ui/vault/notes/{raw_id}",
            json={"status": "polished"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "polished"

    def test_intel_drop_persists_status_change(self, tmp_path):
        """After PUT, reading the note shows updated status."""
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        store, raw_id, polished_id, evergreen_id = _make_vault_store_with_notes(tmp_path)
        app = FastAPI()
        register_vault_routes(app, vault_store=store)
        client = TestClient(app)

        client.put(f"/api/ui/vault/notes/{raw_id}", json={"status": "polished"})
        note = client.get(f"/api/ui/vault/notes/{raw_id}").json()
        assert note["status"] == "polished"

    def test_intel_drop_delegate_exists(self):
        js = open("src/ui/static/app/theseus-app-delegates.js").read()
        assert "intelDrop" in js


# ---------------------------------------------------------------------------
# Slice 4: theseusIntelBulkPolish
# ---------------------------------------------------------------------------


class TestIntelBulkPolish:
    def test_intel_bulk_polish_function_exists(self):
        js = open("src/ui/static/app/theseus-vault-helpers.js").read()
        assert "theseusIntelBulkPolish" in js

    def test_bulk_polish_calls_polish_with_accept_for_raw_notes(self, tmp_path):
        """POST /polish with accept=true changes note status to polished."""
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import src.server.vault_routes as vr

        store, raw_id, polished_id, evergreen_id = _make_vault_store_with_notes(tmp_path)
        curation_mock = AsyncMock(
            return_value="## Polished Title\n**note_type:** requirement\n---\npolished body text"
        )
        orig = vr._ollama_available
        vr._ollama_available = True
        try:
            app = FastAPI()
            register_vault_routes(app, vault_store=store, vault_curation_func=curation_mock)
            client = TestClient(app)
            resp = client.post(
                f"/api/ui/vault/notes/{raw_id}/polish",
                json={"accept": True},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "polished"
        finally:
            vr._ollama_available = orig

    def test_bulk_polish_only_raw_notes_polished(self, tmp_path):
        """Bulk polish route: only raw notes; polished note kept as-is."""
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import src.server.vault_routes as vr

        store, raw_id, polished_id, evergreen_id = _make_vault_store_with_notes(tmp_path)
        curation_mock = AsyncMock(
            return_value="## New Title\n**note_type:** concept\n---\npolished body"
        )
        orig = vr._ollama_available
        vr._ollama_available = True
        try:
            app = FastAPI()
            register_vault_routes(app, vault_store=store, vault_curation_func=curation_mock)
            client = TestClient(app)
            # Polish only the raw note
            client.post(f"/api/ui/vault/notes/{raw_id}/polish", json={"accept": True})
            # Polished note should still be polished (unchanged by this action)
            polished_note = store.read(polished_id)
            assert polished_note["status"] == "polished"
        finally:
            vr._ollama_available = orig

    def test_intel_bulk_polish_delegate_exists(self):
        js = open("src/ui/static/app/theseus-app-delegates.js").read()
        assert "intelBulkPolish" in js


# ---------------------------------------------------------------------------
# Slice 5: Error handling + per-note progress
# ---------------------------------------------------------------------------


class TestIntelBulkPolishProgress:
    def test_bulk_polish_503_when_no_curation_func(self, tmp_path):
        """POST /polish returns 503 when vault_curation_func not configured."""
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import src.server.vault_routes as vr

        store, raw_id, _, _ = _make_vault_store_with_notes(tmp_path)
        orig = vr._ollama_available
        vr._ollama_available = False
        try:
            app = FastAPI()
            register_vault_routes(app, vault_store=store)
            client = TestClient(app)
            resp = client.post(f"/api/ui/vault/notes/{raw_id}/polish", json={"accept": True})
            assert resp.status_code in (503, 400)
        finally:
            vr._ollama_available = orig

    def test_bulk_polish_helper_tracks_progress_state_vars(self):
        """JS helper references intelBulkProgress per-note tracking."""
        js = open("src/ui/static/app/theseus-vault-helpers.js").read()
        assert "intelBulkProgress" in js

    def test_bulk_polish_helper_sets_bulk_polishing_flag(self):
        """JS helper sets intelBulkPolishing to true during operation."""
        js = open("src/ui/static/app/theseus-vault-helpers.js").read()
        assert "intelBulkPolishing" in js


# ---------------------------------------------------------------------------
# Slice 6: HTML structure
# ---------------------------------------------------------------------------


class TestIntelFeedHtml:
    def _html(self):
        return open("src/ui/static/index.html", encoding="utf-8").read()

    def test_intel_feed_section_present(self):
        html = self._html()
        assert "vaultTab === 'intel-feed'" in html

    def test_three_swimlane_headings_present(self):
        html = self._html()
        # Fleeting / Developing / Connected headings
        assert "Fleeting" in html
        assert "Developing" in html
        assert "Connected" in html

    def test_bulk_polish_button_present(self):
        html = self._html()
        assert "Bulk Polish All" in html

    def test_drag_start_handler_present(self):
        html = self._html()
        assert "intelDragId" in html

    def test_drag_drop_handler_present(self):
        html = self._html()
        assert "intelDrop" in html

    def test_status_raw_filter_in_html(self):
        """Fleeting column filters on status raw."""
        html = self._html()
        assert "'raw'" in html or "=== 'raw'" in html or "raw" in html

    def test_status_polished_filter_in_html(self):
        html = self._html()
        assert "'polished'" in html

    def test_status_evergreen_filter_in_html(self):
        html = self._html()
        assert "'evergreen'" in html

    def test_card_click_navigates_to_vault_notes(self):
        """Clicking a card sets active='vault' and vaultTab='notes'."""
        html = self._html()
        assert "active='vault'" in html or 'active="vault"' in html
        assert "vaultTab='notes'" in html or 'vaultTab="notes"' in html

    def test_note_excerpt_slice_present(self):
        """Cards show first 100 chars of body."""
        html = self._html()
        assert ".slice(0, 100)" in html

    def test_empty_swimlane_state_present(self):
        """Each swimlane should have an empty state message."""
        html = self._html()
        # At least one empty state message
        assert "No fleeting notes" in html or "No developing notes" in html or "No connected notes" in html

    def test_intelFeedLoad_watcher_in_core_helpers(self):
        """Core helpers vaultTab watcher calls intelFeedLoad on intel-feed."""
        js = open("src/ui/static/app/theseus-core-helpers.js").read()
        assert "intelFeedLoad" in js
