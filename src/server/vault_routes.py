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
    title: str = ""  # optional — AI generates via /preview
    body: str = ""
    type: str = Field(default="raw", alias="note_type")
    topic: str = ""
    source: str = "manual"
    pursuit: str | None = None
    tags: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class NotePreviewRequest(BaseModel):
    body: str


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
    "You are a govcon capture analyst. Classify and title the note. "
    "Return EXACTLY:\nTYPE: <insight|action|risk|theme|question|raw>\n"
    "TITLE: <concise title max 80 chars>\nNo extra text."
)

_POLISH_SYSTEM = (
    "You are a govcon capture analyst. Polish the note and return EXACTLY:\n"
    "TYPE: <insight|action|risk|theme|question|raw>\n"
    "TITLE: <concise title under 80 chars>\n"
    "BODY: <polished note text>\n"
    "No extra text before TYPE: or after the BODY content."
)

_POLISH_PROMPT_TEMPLATE = "Polish this govcon capture note:\n\n{body}"


def _parse_curation_response(raw: str, fallback_body: str) -> tuple[str, str, str]:
    """Parse TYPE:/TITLE:/BODY: structured LLM response.

    Returns ``(title, note_type, body)``.  Falls back to the legacy
    single-line format (line 1 = type, line 2 = title) for classify.
    """
    lines = raw.strip().splitlines()
    title = ""
    note_type = ""
    body_lines: list[str] = []
    in_body = False

    for line in lines:
        if not in_body and line.upper().startswith("TYPE:"):
            candidate = line[5:].strip().lower().rstrip(".!,;:")
            if candidate in _VALID_NOTE_TYPES:
                note_type = candidate
        elif not in_body and line.upper().startswith("TITLE:"):
            title = line[6:].strip()[:80]
        elif line.upper().startswith("BODY:"):
            in_body = True
            rest = line[5:].strip()
            if rest:
                body_lines.append(rest)
        elif in_body:
            body_lines.append(line)

    # Legacy fallback: first line = type, second line = title
    if not note_type and lines:
        candidate = lines[0].strip().lower().rstrip(".!,;:")
        if candidate in _VALID_NOTE_TYPES:
            note_type = candidate
            if len(lines) > 1 and not title:
                title = lines[1].strip()[:80]

    if not note_type:
        note_type = "raw"

    body = "\n".join(body_lines).strip() or fallback_body

    if not title:
        words = fallback_body.strip()
        title = (words[:60] + "\u2026") if len(words) > 60 else words

    return title, note_type, body


async def _classify_and_update(
    vault_store: VaultStore,
    note_id: str,
    body: str,
    vault_curation_func: Callable,
) -> None:
    """Background task: infer type + title from body; patch the note."""
    prompt = (
        f"Classify and title this govcon capture note.\n"
        f"TYPE: <insight|action|risk|theme|question|raw>\n"
        f"TITLE: <concise title max 80 chars>\n\n"
        f"Note:\n{body}"
    )
    try:
        raw = await vault_curation_func(prompt, system_prompt=_CLASSIFY_SYSTEM)
        title, note_type, _ = _parse_curation_response(raw, fallback_body=body)
        updates: dict[str, Any] = {"type": note_type}
        if title:
            updates["title"] = title
        vault_store.update(note_id, **updates)
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

    @app.post("/api/ui/vault/preview", tags=["theseus-vault"])
    async def preview_note(payload: NotePreviewRequest) -> JSONResponse:
        """Polish a raw brain-dump and return AI-suggested title, type, and body.

        Returns HTTP 503 when no vault_curation_func is configured.
        """
        if vault_curation_func is None:
            raise HTTPException(
                status_code=503,
                detail="Vault curation LLM not configured",
            )
        prompt = _POLISH_PROMPT_TEMPLATE.format(body=payload.body.strip())
        raw = await vault_curation_func(prompt, system_prompt=_POLISH_SYSTEM)
        title, note_type, body = _parse_curation_response(raw, fallback_body=payload.body)
        return JSONResponse({"type": note_type, "title": title, "body": body})

    @app.post("/api/ui/vault/notes", tags=["theseus-vault"])
    async def create_note(
        payload: NoteCreate,
        background_tasks: BackgroundTasks,
    ) -> JSONResponse:
        """Create a new vault note.

        When the caller omits a title (HITL flow: title already approved by user),
        fires a background task to infer both type and title via AI.
        """
        note = vault_store.create(
            title=payload.title,
            body=payload.body,
            note_type=payload.type,
            topic=payload.topic,
            source=payload.source,
            pursuit=payload.pursuit,
            tags=payload.tags,
        )
        # Only classify in background when no title was provided (no AI preview used)
        if vault_curation_func is not None and not payload.title.strip():
            background_tasks.add_task(
                _classify_and_update,
                vault_store,
                note["id"],
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
