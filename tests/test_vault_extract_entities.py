"""TDD contract tests for #146 — Extract Entities → accept-to-KG.

Vertical slices:
  Slice 1 — EntityProposal shape + extract_entities_from_note wired
  Slice 2 — POST /extract-entities endpoint
  Slice 3 — already_in_kg flag
  Slice 4 — POST /accept-entities endpoint → KG
  Slice 5 — UI state vars + HTML entity proposals pane
  Slice 6 — Accept Selected disabled without active workspace
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Slice 1: EntityProposal shape + extract_entities_from_note real impl
# ---------------------------------------------------------------------------


class TestEntityProposalShape:
    def test_proposal_has_entity_text_field(self):
        from src.server.vault_llm import EntityProposal
        p = EntityProposal(entity_text="CMMC Level 3", entity_type="requirement")
        assert p.entity_text == "CMMC Level 3"

    def test_proposal_has_entity_type_field(self):
        from src.server.vault_llm import EntityProposal
        p = EntityProposal(entity_text="CMMC Level 3", entity_type="requirement")
        assert p.entity_type == "requirement"

    def test_proposal_has_confidence_field_defaulting_to_one(self):
        from src.server.vault_llm import EntityProposal
        p = EntityProposal(entity_text="DISA", entity_type="customer")
        assert p.confidence == 1.0

    def test_proposal_has_already_in_kg_defaulting_to_false(self):
        from src.server.vault_llm import EntityProposal
        p = EntityProposal(entity_text="DISA", entity_type="customer")
        assert p.already_in_kg is False

    def test_proposal_entity_type_in_valid_types(self):
        from src.server.vault_llm import EntityProposal
        from src.ontology.schema import VALID_ENTITY_TYPES
        p = EntityProposal(entity_text="CMMC", entity_type="requirement")
        assert p.entity_type in VALID_ENTITY_TYPES


class TestExtractEntitiesFromNote:
    def test_returns_list(self):
        from src.server.vault_llm import extract_entities_from_note

        async def _run():
            mock_llm = AsyncMock(
                return_value=(
                    "ENTITY: CMMC Level 3 | TYPE: requirement | CONFIDENCE: 0.9\n"
                    "ENTITY: DISA | TYPE: customer | CONFIDENCE: 0.8\n"
                )
            )
            return await extract_entities_from_note(
                "We need CMMC Level 3 compliance. DISA is the customer.",
                llm_func=mock_llm,
            )

        result = asyncio.run(_run())
        assert isinstance(result, list)

    def test_returns_entity_proposals(self):
        from src.server.vault_llm import extract_entities_from_note, EntityProposal

        async def _run():
            mock_llm = AsyncMock(
                return_value=(
                    "ENTITY: CMMC Level 3 | TYPE: requirement | CONFIDENCE: 0.9\n"
                    "ENTITY: DISA | TYPE: organization | CONFIDENCE: 0.8\n"
                )
            )
            return await extract_entities_from_note(
                "We need CMMC Level 3. DISA is the customer.",
                llm_func=mock_llm,
            )

        result = asyncio.run(_run())
        assert len(result) >= 1
        assert all(isinstance(p, EntityProposal) for p in result)

    def test_entity_types_from_valid_set(self):
        from src.server.vault_llm import extract_entities_from_note
        from src.ontology.schema import VALID_ENTITY_TYPES

        async def _run():
            mock_llm = AsyncMock(
                return_value=(
                    "ENTITY: CMMC Level 3 | TYPE: requirement | CONFIDENCE: 0.9\n"
                    "ENTITY: DISA | TYPE: organization | CONFIDENCE: 0.85\n"
                )
            )
            return await extract_entities_from_note(
                "CMMC Level 3. DISA.",
                llm_func=mock_llm,
            )

        result = asyncio.run(_run())
        for proposal in result:
            assert proposal.entity_type in VALID_ENTITY_TYPES, (
                f"entity_type '{proposal.entity_type}' not in VALID_ENTITY_TYPES"
            )

    def test_prompt_contains_entity_types(self):
        from src.server.vault_llm import extract_entities_from_note
        from src.ontology.schema import VALID_ENTITY_TYPES

        captured = {}

        async def _capturing_llm(prompt, system_prompt=None, **kwargs):
            captured["prompt"] = prompt
            captured["system"] = system_prompt or ""
            return "ENTITY: CMMC | TYPE: requirement | CONFIDENCE: 0.9\n"

        asyncio.run(extract_entities_from_note("CMMC note", llm_func=_capturing_llm))
        full_text = captured.get("prompt", "") + captured.get("system", "")
        found = any(et in full_text for et in VALID_ENTITY_TYPES)
        assert found, "At least one entity type must appear in the extraction prompt"


# ---------------------------------------------------------------------------
# Slice 2: POST /extract-entities endpoint
# ---------------------------------------------------------------------------


def _make_vault_store_with_note(tmp_path):
    from src.server.vault_store import VaultStore

    store = VaultStore(vault_dir=tmp_path, now=lambda: "2026-05-13T00:00:00Z")
    note = store.create(
        title="DISA RFP Note",
        body="DISA released an RFP requiring CMMC Level 3 compliance.",
        note_type="raw",
        topic="",
        source="manual",
    )
    return store, note["id"]


class TestExtractEntitiesEndpoint:
    def test_extract_returns_200_and_proposals_list(self, tmp_path):
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import src.server.vault_routes as vr

        store, note_id = _make_vault_store_with_note(tmp_path)
        curation_mock = AsyncMock(
            return_value="ENTITY: CMMC Level 3 | TYPE: requirement | CONFIDENCE: 0.9\n"
        )
        orig = vr._ollama_available
        vr._ollama_available = True
        try:
            app = FastAPI()
            register_vault_routes(app, vault_store=store, vault_curation_func=curation_mock)
            client = TestClient(app)
            resp = client.post(f"/api/ui/vault/notes/{note_id}/extract-entities")
            assert resp.status_code == 200
            data = resp.json()
            assert "proposals" in data
            assert isinstance(data["proposals"], list)
        finally:
            vr._ollama_available = orig

    def test_extract_calls_llm_with_note_body(self, tmp_path):
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import src.server.vault_routes as vr

        store, note_id = _make_vault_store_with_note(tmp_path)
        curation_mock = AsyncMock(
            return_value="ENTITY: DISA | TYPE: customer | CONFIDENCE: 0.85\n"
        )
        orig = vr._ollama_available
        vr._ollama_available = True
        try:
            app = FastAPI()
            register_vault_routes(app, vault_store=store, vault_curation_func=curation_mock)
            client = TestClient(app)
            client.post(f"/api/ui/vault/notes/{note_id}/extract-entities")
            curation_mock.assert_awaited_once()
        finally:
            vr._ollama_available = orig

    def test_extract_503_when_no_curation_func(self, tmp_path):
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import src.server.vault_routes as vr

        store, note_id = _make_vault_store_with_note(tmp_path)
        orig = vr._ollama_available
        vr._ollama_available = True
        try:
            app = FastAPI()
            register_vault_routes(app, vault_store=store)
            client = TestClient(app)
            resp = client.post(f"/api/ui/vault/notes/{note_id}/extract-entities")
            assert resp.status_code == 503
        finally:
            vr._ollama_available = orig


# ---------------------------------------------------------------------------
# Slice 3: already_in_kg flag
# ---------------------------------------------------------------------------


class TestAlreadyInKgFlag:
    def test_already_in_kg_true_when_entity_in_workspace(self, tmp_path):
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import src.server.vault_routes as vr

        store, note_id = _make_vault_store_with_note(tmp_path)
        curation_mock = AsyncMock(
            return_value="ENTITY: DISA | TYPE: organization | CONFIDENCE: 0.9\n"
        )
        # entities_func returns DISA as known entity
        entities_mock = AsyncMock(return_value=["DISA", "CMMC"])
        orig = vr._ollama_available
        vr._ollama_available = True
        try:
            app = FastAPI()
            register_vault_routes(
                app,
                vault_store=store,
                vault_curation_func=curation_mock,
                entities_func=entities_mock,
            )
            client = TestClient(app)
            resp = client.post(
                f"/api/ui/vault/notes/{note_id}/extract-entities",
                json={"workspace": "some-workspace"},
            )
            assert resp.status_code == 200
            proposals = resp.json()["proposals"]
            disa = next((p for p in proposals if p["entity_text"] == "DISA"), None)
            assert disa is not None
            assert disa["already_in_kg"] is True
        finally:
            vr._ollama_available = orig

    def test_already_in_kg_false_when_no_workspace(self, tmp_path):
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import src.server.vault_routes as vr

        store, note_id = _make_vault_store_with_note(tmp_path)
        curation_mock = AsyncMock(
            return_value="ENTITY: DISA | TYPE: organization | CONFIDENCE: 0.9\n"
        )
        orig = vr._ollama_available
        vr._ollama_available = True
        try:
            app = FastAPI()
            register_vault_routes(app, vault_store=store, vault_curation_func=curation_mock)
            client = TestClient(app)
            resp = client.post(f"/api/ui/vault/notes/{note_id}/extract-entities")
            proposals = resp.json()["proposals"]
            assert all(p["already_in_kg"] is False for p in proposals)
        finally:
            vr._ollama_available = orig


# ---------------------------------------------------------------------------
# Slice 4: POST /accept-entities endpoint → KG insert
# ---------------------------------------------------------------------------


class TestAcceptEntitiesEndpoint:
    def test_accept_calls_kg_insert_func(self, tmp_path):
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        store, note_id = _make_vault_store_with_note(tmp_path)
        kg_insert_mock = AsyncMock(return_value=None)

        app = FastAPI()
        register_vault_routes(app, vault_store=store, kg_insert_func=kg_insert_mock)
        client = TestClient(app)
        resp = client.post(
            f"/api/ui/vault/notes/{note_id}/accept-entities",
            json={
                "workspace": "my-workspace",
                "proposals": [
                    {"entity_text": "CMMC Level 3", "entity_type": "requirement", "confidence": 0.9, "already_in_kg": False}
                ],
            },
        )
        assert resp.status_code == 200
        kg_insert_mock.assert_awaited_once()

    def test_accept_400_when_no_workspace(self, tmp_path):
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        store, note_id = _make_vault_store_with_note(tmp_path)
        kg_insert_mock = AsyncMock(return_value=None)

        app = FastAPI()
        register_vault_routes(app, vault_store=store, kg_insert_func=kg_insert_mock)
        client = TestClient(app)
        resp = client.post(
            f"/api/ui/vault/notes/{note_id}/accept-entities",
            json={
                "proposals": [
                    {"entity_text": "CMMC", "entity_type": "requirement", "confidence": 0.9, "already_in_kg": False}
                ],
            },
        )
        assert resp.status_code == 400

    def test_accept_503_when_no_kg_insert_func(self, tmp_path):
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        store, note_id = _make_vault_store_with_note(tmp_path)

        app = FastAPI()
        register_vault_routes(app, vault_store=store)
        client = TestClient(app)
        resp = client.post(
            f"/api/ui/vault/notes/{note_id}/accept-entities",
            json={
                "workspace": "my-workspace",
                "proposals": [
                    {"entity_text": "CMMC", "entity_type": "requirement", "confidence": 0.9, "already_in_kg": False}
                ],
            },
        )
        assert resp.status_code == 503

    def test_accept_returns_accepted_count(self, tmp_path):
        from src.server.vault_routes import register_vault_routes
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        store, note_id = _make_vault_store_with_note(tmp_path)
        kg_insert_mock = AsyncMock(return_value=None)

        app = FastAPI()
        register_vault_routes(app, vault_store=store, kg_insert_func=kg_insert_mock)
        client = TestClient(app)
        resp = client.post(
            f"/api/ui/vault/notes/{note_id}/accept-entities",
            json={
                "workspace": "my-workspace",
                "proposals": [
                    {"entity_text": "CMMC Level 3", "entity_type": "requirement", "confidence": 0.9, "already_in_kg": False},
                    {"entity_text": "DISA", "entity_type": "customer", "confidence": 0.85, "already_in_kg": True},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "accepted" in data
        assert data["accepted"] == 2


# ---------------------------------------------------------------------------
# Slice 5: UI state vars + HTML entity proposals pane
# ---------------------------------------------------------------------------
