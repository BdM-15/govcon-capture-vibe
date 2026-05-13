"""Knowledge Vault CRUD routes for Project Theseus UI."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
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
# Route registration
# ---------------------------------------------------------------------------


def register_vault_routes(
    app: FastAPI,
    *,
    vault_store: VaultStore,
) -> None:
    """Mount /api/ui/vault/* routes onto *app*."""

    @app.get("/api/ui/vault/notes", tags=["theseus-vault"])
    async def list_notes() -> JSONResponse:
        """List all vault notes, newest-updated first."""
        return JSONResponse({"notes": vault_store.list_notes()})

    @app.post("/api/ui/vault/notes", tags=["theseus-vault"])
    async def create_note(payload: NoteCreate) -> JSONResponse:
        """Create a new vault note and return it."""
        note = vault_store.create(
            title=payload.title,
            body=payload.body,
            note_type=payload.type,
            topic=payload.topic,
            source=payload.source,
            pursuit=payload.pursuit,
            tags=payload.tags,
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
