from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.briefing_prompts import BRIEFING_PROMPT_LIBRARY
from src.server.prompt_library import (
    PROMPT_LIBRARY,
    PromptEntryCreate,
    PromptEntryUpdate,
    PromptLibraryStore,
    register_prompt_library_routes,
    shipped_defaults,
    shipped_prompt_id,
)


def test_prompt_library_shape_and_phase_coverage() -> None:
    assert PROMPT_LIBRARY
    phases = {prompt["phase"] for prompt in PROMPT_LIBRARY}
    assert phases == {"4", "5", "6"}

    for prompt in PROMPT_LIBRARY:
        assert set(prompt) == {"phase", "category", "title", "prompt"}
        assert prompt["phase"] in {"4", "5", "6"}
        assert prompt["category"].strip()
        assert prompt["title"].strip()
        assert prompt["prompt"].strip()


def test_shipped_defaults_have_stable_ids() -> None:
    defaults = shipped_defaults()
    assert len(defaults) == len(PROMPT_LIBRARY) + len(BRIEFING_PROMPT_LIBRARY)
    ids = [entry["id"] for entry in defaults]
    assert len(ids) == len(set(ids))
    first = defaults[0]
    assert first["source"] == "shipped"
    assert first["id"] == shipped_prompt_id(
        first["phase"], first["category"], first["title"]
    )


def test_store_read_without_overrides_matches_defaults(tmp_path: Path) -> None:
    store = PromptLibraryStore(workspace_dir=lambda: tmp_path)
    assert store.read() == store.defaults()
    assert not store.customized()


def test_store_add_update_delete_custom(tmp_path: Path) -> None:
    store = PromptLibraryStore(workspace_dir=lambda: tmp_path)
    created = store.add(
        PromptEntryCreate(
            phase="4",
            category="Discovery",
            title="My custom primer",
            prompt="Explain scope with [N] citations.",
        )
    )
    assert created["source"] == "user"
    merged = store.read()
    assert any(item["title"] == "My custom primer" for item in merged)
    assert store.customized()

    store.update(created["id"], PromptEntryUpdate(title="Updated primer"))
    updated = next(item for item in store.read() if item["id"] == created["id"])
    assert updated["title"] == "Updated primer"

    store.delete(created["id"])
    assert not any(item["id"] == created["id"] for item in store.read())


def test_store_override_shipped_and_hide(tmp_path: Path) -> None:
    store = PromptLibraryStore(workspace_dir=lambda: tmp_path)
    shipped = store.defaults()[0]
    store.update(
        shipped["id"],
        PromptEntryUpdate(prompt="Edited shipped prompt body."),
    )
    edited = next(item for item in store.read() if item["id"] == shipped["id"])
    assert edited["prompt"] == "Edited shipped prompt body."
    assert edited["source"] == "shipped"

    store.delete(shipped["id"])
    assert not any(item["id"] == shipped["id"] for item in store.read())

    store.reset()
    assert store.read() == store.defaults()


def test_store_duplicate_creates_user_copy(tmp_path: Path) -> None:
    store = PromptLibraryStore(workspace_dir=lambda: tmp_path)
    source = store.defaults()[0]
    copy = store.duplicate(source["id"])
    assert copy["source"] == "user"
    assert copy["title"].endswith("(copy)")
    assert copy["prompt"] == source["prompt"]


@pytest.fixture()
def prompt_client(tmp_path: Path) -> TestClient:
    store = PromptLibraryStore(workspace_dir=lambda: tmp_path)

    async def fake_llm(prompt: str) -> str:
        return "Refined prompt text with [N] citations."

    app = FastAPI()
    register_prompt_library_routes(
        app,
        workspace_name=lambda: "test_ws",
        store=store,
        llm_func=fake_llm,
    )
    return TestClient(app)


def test_prompt_library_route_returns_catalog(prompt_client: TestClient) -> None:
    response = prompt_client.get("/api/ui/prompt-library")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workspace"] == "test_ws"
    assert body["customized"] is False
    assert len(body["prompts"]) == len(PROMPT_LIBRARY) + len(BRIEFING_PROMPT_LIBRARY)
    assert body["prompts"][0]["source"] == "shipped"
    assert "id" in body["prompts"][0]


def test_prompt_library_crud_routes(prompt_client: TestClient, tmp_path: Path) -> None:
    create = prompt_client.post(
        "/api/ui/prompt-library",
        json={
            "phase": "5",
            "category": "Writing",
            "title": "Custom section draft",
            "prompt": "Draft section {section_or_task} with [N] citations.",
        },
    )
    assert create.status_code == 200, create.text
    entry_id = create.json()["entry"]["id"]

    update = prompt_client.put(
        f"/api/ui/prompt-library/{entry_id}",
        json={"title": "Renamed custom draft"},
    )
    assert update.status_code == 200, update.text
    assert any(
        item["title"] == "Renamed custom draft"
        for item in update.json()["prompts"]
    )

    dup = prompt_client.post(f"/api/ui/prompt-library/{entry_id}/duplicate")
    assert dup.status_code == 200, dup.text
    assert len(dup.json()["prompts"]) == len(PROMPT_LIBRARY) + len(BRIEFING_PROMPT_LIBRARY) + 2

    delete = prompt_client.delete(f"/api/ui/prompt-library/{entry_id}")
    assert delete.status_code == 200, delete.text

    reset = prompt_client.post("/api/ui/prompt-library/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["customized"] is False
    assert not (tmp_path / "ui_prompt_library.json").exists()


def test_skill_default_prompt_route(prompt_client: TestClient) -> None:
    response = prompt_client.get(
        "/api/ui/prompt-library/skill-default/mission-readiness-framer"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skill"] == "mission-readiness-framer"
    assert "mission_readiness_frame.json" in body["entry"]["prompt"]


def test_prompt_library_import_and_refine(prompt_client: TestClient) -> None:
    imported = prompt_client.post(
        "/api/ui/prompt-library/import",
        json={
            "prompts": [
                {
                    "phase": "6",
                    "category": "Review",
                    "title": "Imported review prompt",
                    "prompt": "Review volume {volume_or_section}.",
                }
            ]
        },
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["customized"] is True

    refined = prompt_client.post(
        "/api/ui/prompt-library/refine",
        json={"prompt": "Summarize scope.", "action": "citations"},
    )
    assert refined.status_code == 200, refined.text
    assert "Refined prompt" in refined.json()["prompt"]