"""Tests for #145 â€” vault_llm deep module + updated polish endpoint + diff preview."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# vault_llm module
# ---------------------------------------------------------------------------


class TestVaultLlmModule:
    def test_polish_result_shape(self):
        from src.server.vault_llm import PolishResult
        r = PolishResult(
            original="old",
            rewritten="new",
            diff_hunks=["- old", "+ new"],
            wikilink_suggestions=["[[Some Note]]"],
        )
        assert r.original == "old"
        assert r.rewritten == "new"
        assert isinstance(r.diff_hunks, list)
        assert isinstance(r.wikilink_suggestions, list)

    def test_polish_note_returns_polish_result(self):
        from src.server.vault_llm import polish_note, PolishResult

        async def _run():
            mock_llm = AsyncMock(
                return_value="TYPE: insight\nTITLE: Clean Note\nBODY: This note covers cloud migration and CMMC compliance."
            )
            result = await polish_note(
                raw_body="raw brain dump about cloud and cmmc",
                note_type="raw",
                model_role="vault_curation",
                vault_index={"Cloud Migration Plan": "cloud-migration-plan"},
                llm_func=mock_llm,
            )
            return result

        result = asyncio.run(_run())
        assert isinstance(result, PolishResult)
        assert result.original == "raw brain dump about cloud and cmmc"
        assert len(result.rewritten) > 0

    def test_diff_hunks_computed_when_body_changed(self):
        from src.server.vault_llm import polish_note

        async def _run():
            mock_llm = AsyncMock(
                return_value="TYPE: insight\nTITLE: Better\nBODY: This is a completely rewritten body."
            )
            result = await polish_note(
                raw_body="original body content here",
                note_type="raw",
                model_role="vault_curation",
                vault_index={},
                llm_func=mock_llm,
            )
            return result

        result = asyncio.run(_run())
        assert len(result.diff_hunks) > 0

    def test_wikilink_suggestions_from_vault_index(self):
        from src.server.vault_llm import polish_note

        async def _run():
            # LLM returns text mentioning "cloud migration"
            mock_llm = AsyncMock(
                return_value=(
                    "TYPE: insight\nTITLE: Strategy\n"
                    "BODY: We need to focus on cloud migration as part of our zero trust approach."
                )
            )
            result = await polish_note(
                raw_body="cloud migration zero trust",
                note_type="raw",
                model_role="vault_curation",
                vault_index={"Cloud Migration Plan": "cloud-migration-plan", "Unrelated Note": "unrelated"},
                llm_func=mock_llm,
            )
            return result

        result = asyncio.run(_run())
        # "Cloud Migration Plan" words appear in the polished body â†’ suggestion
        assert any("Cloud Migration Plan" in s for s in result.wikilink_suggestions)
        # "Unrelated Note" words don't appear â†’ no suggestion
        assert not any("Unrelated Note" in s for s in result.wikilink_suggestions)

    def test_polish_note_prompt_contains_entity_types(self):
        """LLM is called with a prompt that includes govcon entity type names."""
        from src.server.vault_llm import polish_note
        from src.ontology.schema import VALID_ENTITY_TYPES

        captured_prompt = {}

        async def _capturing_llm(prompt, system_prompt=None, **kwargs):
            captured_prompt["prompt"] = prompt
            captured_prompt["system"] = system_prompt
            return "TYPE: raw\nTITLE: t\nBODY: b"

        async def _run():
            await polish_note(
                raw_body="some note",
                note_type="raw",
                model_role="vault_curation",
                vault_index={},
                llm_func=_capturing_llm,
            )

        asyncio.run(_run())
        full_text = (captured_prompt.get("prompt") or "") + (captured_prompt.get("system") or "")
        # At least one entity type should appear in the prompt
        found = any(et in full_text for et in VALID_ENTITY_TYPES)
        assert found, f"No entity type found in prompt. Sample types: {list(VALID_ENTITY_TYPES)[:5]}"

    def test_extract_entities_with_llm_func_returns_list(self):
        from src.server.vault_llm import extract_entities_from_note
        from unittest.mock import AsyncMock

        async def _run():
            mock_llm = AsyncMock(
                return_value="ENTITY: CMMC Level 3 | TYPE: requirement | CONFIDENCE: 0.9\n"
            )
            return await extract_entities_from_note("some govcon note body", llm_func=mock_llm)

        result = asyncio.run(_run())
        assert isinstance(result, list)

    def test_ask_theseus_stub_returns_str(self):
        from src.server.vault_llm import ask_theseus_about_note

        async def _run():
            return await ask_theseus_about_note("some note body", "some_workspace")

        result = asyncio.run(_run())
        assert isinstance(result, str)

    def test_no_fastapi_import_in_vault_llm(self):
        """vault_llm must not import FastAPI (pure async, independently testable)."""
        content = Path("src/server/vault_llm.py").read_text(encoding="utf-8")
        assert "from fastapi" not in content
        assert "import fastapi" not in content


# ---------------------------------------------------------------------------
# Updated polish endpoint
# ---------------------------------------------------------------------------


def _make_store_and_note(tmp_path, note_id="n1"):
    from src.server.vault_store import VaultStore

    def _now():
        return "2026-05-13T00:00:00Z"

    store = VaultStore(vault_dir=tmp_path, now=_now)
    note = store.create(
        title="Raw Note",
        body="Our team should work on cloud migration and zero trust security.",
        note_type="raw",
        topic="",
        source="manual",
    )
    return store, note["id"]


class TestPolishEndpointUpdated:
    def test_polish_no_accept_returns_diff_not_store(self, tmp_path):
        """POST /polish without accept=true returns PolishResult, does NOT update store."""
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import src.server.vault_routes as vr

        store, note_id = _make_store_and_note(tmp_path)
        curation_mock = AsyncMock(
            return_value="TYPE: insight\nTITLE: Better\nBODY: Polished body about cloud migration."
        )
        orig = vr._ollama_available
        vr._ollama_available = True
        try:
            app = FastAPI()
            register_vault_routes(app, vault_store=store, vault_curation_func=curation_mock)
            client = TestClient(app)
            resp = client.post(
                f"/api/ui/vault/notes/{note_id}/polish",
                json={"model": "qwen", "accept": False},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "original" in data
            assert "rewritten" in data
            assert "diff_hunks" in data
            assert "wikilink_suggestions" in data
            # Note body should NOT have been modified
            note_after = store.read(note_id)
            assert note_after["body"] == "Our team should work on cloud migration and zero trust security."
            assert note_after.get("status") != "polished"
        finally:
            vr._ollama_available = orig

    def test_polish_with_accept_updates_store(self, tmp_path):
        """POST /polish with accept=true rewrites note body and sets status=polished."""
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import src.server.vault_routes as vr

        store, note_id = _make_store_and_note(tmp_path)
        curation_mock = AsyncMock(
            return_value="TYPE: insight\nTITLE: Polished Title\nBODY: Polished body about cloud migration."
        )
        orig = vr._ollama_available
        vr._ollama_available = True
        try:
            app = FastAPI()
            register_vault_routes(app, vault_store=store, vault_curation_func=curation_mock)
            client = TestClient(app)
            resp = client.post(
                f"/api/ui/vault/notes/{note_id}/polish",
                json={"model": "qwen", "accept": True},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("status") == "polished"
            note_after = store.read(note_id)
            assert note_after["status"] == "polished"
            assert note_after["body"] != "Our team should work on cloud migration and zero trust security."
        finally:
            vr._ollama_available = orig

    def test_polish_grok_model_uses_query_func(self, tmp_path):
        """model=grok routes to query_func, not vault_curation_func."""
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import src.server.vault_routes as vr

        store, note_id = _make_store_and_note(tmp_path)
        curation_mock = AsyncMock(return_value="TYPE: raw\nTITLE: x\nBODY: from curation")
        query_mock = AsyncMock(return_value="TYPE: insight\nTITLE: Better\nBODY: from grok")
        orig = vr._ollama_available
        vr._ollama_available = True
        try:
            app = FastAPI()
            register_vault_routes(
                app,
                vault_store=store,
                vault_curation_func=curation_mock,
                query_func=query_mock,
            )
            client = TestClient(app)
            resp = client.post(
                f"/api/ui/vault/notes/{note_id}/polish",
                json={"model": "grok", "accept": False},
            )
            assert resp.status_code == 200
            curation_mock.assert_not_awaited()
            query_mock.assert_awaited_once()
        finally:
            vr._ollama_available = orig

    def test_polish_no_accept_default_is_preview(self, tmp_path):
        """Default body (no JSON) behaves as preview (backward compat â€” does not update note)."""
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import src.server.vault_routes as vr

        store, note_id = _make_store_and_note(tmp_path)
        curation_mock = AsyncMock(
            return_value="TYPE: insight\nTITLE: Better\nBODY: Polished body."
        )
        orig = vr._ollama_available
        vr._ollama_available = True
        try:
            app = FastAPI()
            register_vault_routes(app, vault_store=store, vault_curation_func=curation_mock)
            client = TestClient(app)
            # No JSON body = defaults
            resp = client.post(f"/api/ui/vault/notes/{note_id}/polish")
            assert resp.status_code == 200
            data = resp.json()
            # Returns diff preview shape
            assert "diff_hunks" in data
        finally:
            vr._ollama_available = orig


class TestAutoPolish:
    def test_auto_polish_on_create(self, tmp_path):
        """vault_auto_polish=True causes POST /notes to polish and set status=polished."""
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import src.server.vault_routes as vr

        from src.server.vault_store import VaultStore

        def _now():
            return "2026-05-13T00:00:00Z"

        store = VaultStore(vault_dir=tmp_path, now=_now)
        curation_mock = AsyncMock(
            return_value="TYPE: insight\nTITLE: Auto Polished\nBODY: Auto-polished body."
        )
        orig = vr._ollama_available
        vr._ollama_available = True
        try:
            app = FastAPI()
            register_vault_routes(
                app,
                vault_store=store,
                vault_curation_func=curation_mock,
                vault_auto_polish=True,
            )
            client = TestClient(app)
            resp = client.post(
                "/api/ui/vault/notes",
                json={"title": "Draft Note", "body": "Some raw body", "note_type": "raw", "topic": "", "source": "manual"},
            )
            assert resp.status_code == 201
            created_id = resp.json()["id"]
            # Give background task time to run
            note = store.read(created_id)
            assert note["status"] == "polished", "Auto-polish should have set status=polished"
        finally:
            vr._ollama_available = orig


# ---------------------------------------------------------------------------
# Frontend: state vars
# ---------------------------------------------------------------------------


class TestVaultDiffState:
    def test_vault_diff_state_vars_present(self):
        src_text = Path("src/ui/static/app/theseus-state-helpers.js").read_text(encoding="utf-8")
        assert "vaultDiffResult" in src_text
        assert "vaultDiffOpen" in src_text
        assert "vaultPolishModel" in src_text
        assert "vaultPolishLoading" in src_text


# ---------------------------------------------------------------------------
# Frontend: helpers
# ---------------------------------------------------------------------------

class TestVaultDiffDelegates:
    def test_vault_diff_delegates_wired(self):
        src_text = Path("src/ui/static/app/theseus-app-delegates.js").read_text(encoding="utf-8")
        assert "vaultPreviewPolish" in src_text
        assert "vaultAcceptPolish" in src_text


# ---------------------------------------------------------------------------
# Frontend: HTML
# ---------------------------------------------------------------------------
