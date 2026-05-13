"""Knowledge Vault CRUD routes for Project Theseus UI."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.server.vault_store import VaultStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ollama availability state (set by app.py at startup)
# ---------------------------------------------------------------------------

_ollama_available: bool = False


def set_ollama_available(available: bool) -> None:
    """Called at startup to record whether Ollama is reachable."""
    global _ollama_available
    _ollama_available = available


def is_ollama_available() -> bool:
    """Return current Ollama availability flag."""
    return _ollama_available


def _require_ollama() -> None:
    """Raise 503 if Ollama is not reachable (for polish-related routes)."""
    if not _ollama_available:
        raise HTTPException(
            status_code=503,
            detail="Vault curation LLM (Ollama) is not reachable. "
                   "Start Ollama and restart Theseus to enable polish endpoints.",
        )


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class NoteCreate(BaseModel):
    title: str
    body: str = ""
    type: str = Field(default="raw_idea", alias="note_type")
    topic: str = ""
    source: str = "manual"
    pursuit: str | None = None
    tags: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class NoteUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    type: str | None = Field(default=None, alias="note_type")
    topic: str | None = None
    source: str | None = None
    status: str | None = None
    pursuit: str | None = None
    tags: list[str] | None = None

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Background classification
# ---------------------------------------------------------------------------

_VALID_NOTE_TYPES = frozenset({"insight", "action", "risk", "theme", "question", "raw"})

_CLASSIFY_SYSTEM = (
    "You are a govcon capture analyst. Classify the note into exactly one type. "
    "Respond with one word only."
)


async def _classify_and_update(
    vault_store: VaultStore,
    note_id: str,
    title: str,
    body: str,
    vault_curation_func: Callable,
) -> None:
    """Background task: call vault_curation_func, infer type, patch the note."""
    prompt = (
        f"Classify this capture note into exactly one of: "
        f"insight|action|risk|theme|question|raw\n"
        f"Title: {title}\nBody: {body}\nRespond with one word only."
    )
    try:
        raw = await vault_curation_func(prompt, system_prompt=_CLASSIFY_SYSTEM)
        inferred = raw.strip().lower().split()[0] if raw.strip() else "raw"
        # Strip punctuation in case the model adds it
        inferred = inferred.rstrip(".!,;:")
        if inferred not in _VALID_NOTE_TYPES:
            inferred = "raw"
        vault_store.update(note_id, type=inferred)
    except Exception:
        logger.exception("Vault background classify failed for note %s", note_id)


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def register_vault_routes(
    app: FastAPI,
    *,
    vault_store: VaultStore,
    vault_curation_func: Callable | None = None,
) -> None:
    """Mount /api/ui/vault/* routes onto *app*."""

    @app.get("/api/ui/vault/notes", tags=["theseus-vault"])
    async def list_notes() -> JSONResponse:
        """List all vault notes, newest-updated first."""
        return JSONResponse({"notes": vault_store.list_notes()})

    @app.post("/api/ui/vault/notes", tags=["theseus-vault"])
    async def create_note(
        payload: NoteCreate,
        background_tasks: BackgroundTasks,
    ) -> JSONResponse:
        """Create a new vault note. If vault_curation_func is wired, AI classifies type in background."""
        note = vault_store.create(
            title=payload.title,
            body=payload.body,
            note_type=payload.type,
            topic=payload.topic,
            source=payload.source,
            pursuit=payload.pursuit,
            tags=payload.tags,
        )
        if vault_curation_func is not None:
            background_tasks.add_task(
                _classify_and_update,
                vault_store,
                note["id"],
                payload.title,
                payload.body,
                vault_curation_func,
            )
        return JSONResponse(note, status_code=201)

    @app.get("/api/ui/vault/notes/{note_id}", tags=["theseus-vault"])
    async def get_note(note_id: str) -> JSONResponse:
        """Return a single vault note by id."""
        return JSONResponse(vault_store.read(note_id))

    @app.put("/api/ui/vault/notes/{note_id}", tags=["theseus-vault"])
    async def update_note(note_id: str, payload: NoteUpdate) -> JSONResponse:
        """Patch one or more fields on an existing vault note."""
        updates: dict[str, Any] = {
            k: v
            for k, v in payload.model_dump(by_alias=False).items()
            if v is not None
        }
        # map pydantic field name 'type' back to frontmatter key
        note = vault_store.update(note_id, **updates)
        return JSONResponse(note)

    @app.delete("/api/ui/vault/notes/{note_id}", tags=["theseus-vault"])
    async def delete_note(note_id: str) -> JSONResponse:
        """Permanently delete a vault note."""
        vault_store.delete(note_id)
        return JSONResponse({"status": "deleted", "id": note_id})

    @app.post("/api/ui/vault/notes/{note_id}/polish", tags=["theseus-vault"])
    async def polish_note(note_id: str) -> JSONResponse:
        """Polish a vault note via the vault_curation LLM (requires Ollama)."""
        _require_ollama()
        # Full polish logic lives in a future issue; this stub proves the 503 gate.
        return JSONResponse({"status": "not_implemented"}, status_code=501)
