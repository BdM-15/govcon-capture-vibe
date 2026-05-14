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
    tier: str | None = None

    model_config = {"populate_by_name": True}


class NotePreviewRequest(BaseModel):
    body: str


class CaptureRequest(BaseModel):
    """Body for POST /api/ui/vault/capture."""
    body: str
    auto_polish: bool | None = None  # None = use server default (vault_auto_polish)


class NoteUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    type: str | None = Field(default=None, alias="note_type")
    topic: str | None = None
    source: str | None = None
    status: str | None = None
    pursuit: str | None = None
    tags: list[str] | None = None
    tier: str | None = None

    model_config = {"populate_by_name": True}


class PolishRequest(BaseModel):
    """Body for POST /notes/{id}/polish."""
    model: str = "qwen"  # "qwen" (Ollama vault_curation) or "grok" (Grok query)
    accept: bool = False  # False = preview only; True = persist to store


# ---------------------------------------------------------------------------
# Background classification
# ---------------------------------------------------------------------------

_VALID_NOTE_TYPES = frozenset({
    "insight", "action", "risk", "theme", "question", "raw",
    "article", "shipley_ref", "capability", "lesson_learned",
})

_TYPE_LIST = "insight|action|risk|theme|question|raw|article|shipley_ref|capability|lesson_learned"

_CLASSIFY_SYSTEM = (
    "You are a govcon capture analyst. Classify and title the note. "
    f"Return EXACTLY:\nTYPE: <{_TYPE_LIST}>\n"
    "TITLE: <concise title max 80 chars>\nNo extra text."
)

_POLISH_SYSTEM = (
    "You are a govcon capture analyst. Polish the note and return EXACTLY:\n"
    f"TYPE: <{_TYPE_LIST}>\n"
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


async def _auto_polish_note(
    vault_store: VaultStore,
    note_id: str,
    body: str,
    vault_curation_func: Callable,
) -> None:
    """Background task: polish a newly created note and persist the result."""
    from src.server.vault_llm import polish_note as _llm_polish

    try:
        vault_index: dict[str, str] = {
            n["title"]: n["id"] for n in vault_store.list_notes() if n.get("title")
        }
        result = await _llm_polish(
            raw_body=body,
            note_type="raw",
            model_role="vault_curation",
            vault_index=vault_index,
            llm_func=vault_curation_func,
        )
        vault_store.update(
            note_id,
            title=result.title or body[:60],
            type=result.note_type,
            body=result.rewritten,
            status="polished",
        )
    except Exception:
        logger.exception("Vault auto-polish failed for note %s", note_id)


async def _classify_and_update(
    vault_store: VaultStore,
    note_id: str,
    body: str,
    vault_curation_func: Callable,
) -> None:
    """Background task: infer type + title from body; patch the note."""
    prompt = (
        f"Classify and title this govcon capture note.\n"
        f"TYPE: <{_TYPE_LIST}>\n"
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


class AskTheseusRequest(BaseModel):
    workspace: str | None = None


class SaveAsNoteRequest(BaseModel):
    answer: str
    source_title: str = ""


class FeedToWorkspaceRequest(BaseModel):
    workspace: str


class EntityProposalItem(BaseModel):
    entity_text: str
    entity_type: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    already_in_kg: bool = False


class ExtractEntitiesRequest(BaseModel):
    workspace: str | None = None


class AcceptEntitiesRequest(BaseModel):
    workspace: str | None = None
    proposals: list[EntityProposalItem] = Field(default_factory=list)


def _score_note(note: dict, entity_terms: list[str]) -> float:
    """Keyword-overlap score between a vault note and a list of entity terms.

    Each entity term contributes its word tokens; the score is the sum of
    matching token occurrences (case-insensitive) normalised by note length.
    """
    text = ((note.get("title") or "") + " " + (note.get("body") or "")).lower()
    if not text.strip() or not entity_terms:
        return 0.0
    tokens: list[str] = []
    for term in entity_terms:
        tokens.extend(w for w in term.lower().split() if len(w) > 2)
    if not tokens:
        return 0.0
    hits = sum(text.count(tok) for tok in tokens)
    doc_len = max(len(text.split()), 1)
    return round(hits / doc_len, 4)


def register_vault_routes(
    app: FastAPI,
    *,
    vault_store: VaultStore,
    vault_curation_func: Callable | None = None,
    query_func: Callable | None = None,
    entities_func: Callable | None = None,
    kg_insert_func: Callable | None = None,
    vault_auto_polish: bool = False,
) -> None:
    """Mount /api/ui/vault/* routes onto *app*."""

    @app.get("/api/ui/vault/notes", tags=["theseus-vault"])
    async def list_notes(
        q: str | None = None,
        type: str | None = None,
        status: str | None = None,
        topic: str | None = None,
        pursuit: str | None = None,
        tier: str | None = None,
    ) -> JSONResponse:
        """List vault notes with optional search (q) and field filters."""
        notes = vault_store.list_notes()
        if q:
            q_lower = q.lower()
            notes = [
                n for n in notes
                if q_lower in (n.get("title") or "").lower()
                or q_lower in (n.get("body") or "").lower()
            ]
        if type:
            notes = [n for n in notes if n.get("type") == type]
        if status:
            notes = [n for n in notes if n.get("status") == status]
        if topic:
            notes = [n for n in notes if n.get("topic") == topic]
        if pursuit:
            notes = [n for n in notes if n.get("pursuit") == pursuit]
        if tier:
            notes = [n for n in notes if n.get("tier") == tier]
        return JSONResponse({"notes": notes})

    @app.get("/api/ui/vault/stream", tags=["theseus-vault"])
    async def stream_notes(
        tier: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> JSONResponse:
        """Capture-Stream feed: filter by tier/status, cap with limit. Newest first."""
        valid_tiers = {"doctrine", "intelligence", "pursuit"}
        valid_statuses = {"raw", "polished", "evergreen"}
        if tier and tier not in valid_tiers:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid tier '{tier}'. Allowed: {sorted(valid_tiers)}",
            )
        if status and status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Allowed: {sorted(valid_statuses)}",
            )
        notes = vault_store.list_notes()
        if tier:
            notes = [n for n in notes if n.get("tier") == tier]
        if status:
            notes = [n for n in notes if n.get("status") == status]
        if limit is not None and limit >= 0:
            notes = notes[:limit]
        return JSONResponse({"notes": notes})

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

    @app.post("/api/ui/vault/capture", tags=["theseus-vault"])
    async def capture_note(payload: CaptureRequest) -> JSONResponse:
        """Single-shot capture: classify + polish (optional) + persist.

        Wraps `vault_capture.capture(...)`.  Returns 503 when auto_polish is
        on but no vault_curation_func is configured.
        """
        from src.server.vault_capture import capture as _capture
        from dataclasses import asdict

        do_polish = (
            vault_auto_polish if payload.auto_polish is None else payload.auto_polish
        )
        if do_polish and vault_curation_func is None:
            raise HTTPException(
                status_code=503,
                detail="Vault curation LLM not configured",
            )

        # Build title -> slug index from existing notes for wikilink scoring
        vault_index = {
            (n.get("title") or n["id"]): n["id"]
            for n in vault_store.list_notes()
        }
        try:
            captured = await _capture(
                raw_body=payload.body,
                llm_func=vault_curation_func,  # type: ignore[arg-type]
                vault_store=vault_store,
                vault_index=vault_index,
                auto_polish=do_polish,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        result = asdict(captured)
        result["path"] = str(result["path"])
        return JSONResponse(result)


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
            tier=payload.tier,
        )
        # Auto-polish immediately (background task) if feature is enabled
        if vault_auto_polish and vault_curation_func is not None:
            background_tasks.add_task(
                _auto_polish_note,
                vault_store,
                note["id"],
                payload.body,
                vault_curation_func,
            )
        elif vault_curation_func is not None and not payload.title.strip():
            # Only classify in background when no title was provided (no AI preview used)
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
    async def polish_note(
        note_id: str,
        payload: PolishRequest = PolishRequest(),
    ) -> JSONResponse:
        """Polish a vault note and return a diff preview or persist changes.

        - ``accept=False`` (default): runs the LLM, returns PolishResult (diff
          preview). Note is NOT modified — safe for UI preview.
        - ``accept=True``: rewrites the note body and sets status=polished.
        - ``model="qwen"`` (default): uses vault_curation_func (Ollama).
        - ``model="grok"``: uses query_func (Grok cloud); Ollama not required.
        """
        from src.server.vault_llm import polish_note as _llm_polish

        # Select LLM func and guard availability
        if payload.model == "grok":
            if query_func is None:
                raise HTTPException(status_code=503, detail="Grok query LLM not configured")
            llm_func = query_func
        else:
            _require_ollama()
            if vault_curation_func is None:
                raise HTTPException(status_code=503, detail="Vault curation LLM not configured")
            llm_func = vault_curation_func

        note = vault_store.read(note_id)
        vault_index = {n["title"]: n["id"] for n in vault_store.list_notes() if n.get("title")}

        result = await _llm_polish(
            raw_body=note["body"],
            note_type=note.get("type", "raw"),
            model_role=payload.model,
            vault_index=vault_index,
            llm_func=llm_func,
        )

        if not payload.accept:
            # Preview mode — return diff, do not persist
            return JSONResponse({
                "original": result.original,
                "rewritten": result.rewritten,
                "diff_hunks": result.diff_hunks,
                "wikilink_suggestions": result.wikilink_suggestions,
            })

        # Accept mode — persist the polished body and metadata
        updated = vault_store.update(
            note_id,
            title=result.title or note.get("title", ""),
            type=result.note_type,
            body=result.rewritten,
            status="polished",
        )
        return JSONResponse(updated)

    _STATUS_LADDER = {"raw": "polished", "polished": "evergreen", "evergreen": "evergreen"}

    @app.post("/api/ui/vault/notes/{note_id}/promote", tags=["theseus-vault"])
    async def promote_note(note_id: str) -> JSONResponse:
        """Advance a note's status: raw→polished→evergreen (idempotent at evergreen)."""
        note = vault_store.read(note_id)
        current = note.get("status") or "raw"
        next_status = _STATUS_LADDER.get(current, "polished")
        if next_status != current:
            note = vault_store.update(note_id, status=next_status)
        return JSONResponse(note)

    # ---------------------------------------------------------------------------
    # Ask Theseus
    # ---------------------------------------------------------------------------

    _ASK_VAULT_FALLBACK = (
        "No connected workspace. Based on vault notes matching your query:\n\n{snippets}"
    )

    @app.post("/api/ui/vault/notes/{note_id}/ask-theseus", tags=["theseus-vault"])
    async def ask_theseus(note_id: str, payload: AskTheseusRequest = AskTheseusRequest()) -> JSONResponse:
        """Query workspace KG (or vault) using the note body as context."""
        note = vault_store.read(note_id)  # raises 404 if missing
        query_text = note.get("body") or note.get("title") or ""

        if query_func is not None:
            try:
                answer_text = await query_func(query_text, "hybrid", [], False, {})
                if not isinstance(answer_text, str):
                    answer_text = str(answer_text)
            except Exception:
                logger.exception("ask-theseus workspace_kg query failed for note %s", note_id)
                answer_text = "Query failed — check workspace connectivity."
            return JSONResponse({"answer": answer_text, "sources": [], "mode": "workspace_kg"})

        # Vault-only fallback: fulltext search of all notes
        all_notes = vault_store.list_notes()
        q_lower = query_text.lower()[:200]
        matches = [
            n for n in all_notes
            if n["id"] != note_id
            and (q_lower[:40] in (n.get("title") or "").lower()
                 or any(w in (n.get("body") or "").lower() for w in q_lower.split()[:6] if len(w) > 3))
        ][:5]
        sources = [{"note_id": n["id"], "title": n.get("title", "")} for n in matches]
        snippets = "\n\n".join(
            f"**{n.get('title', 'Note')}**: {(n.get('body') or '')[:200]}" for n in matches
        ) or "No closely related notes found."
        answer_text = _ASK_VAULT_FALLBACK.format(snippets=snippets)
        return JSONResponse({"answer": answer_text, "sources": sources, "mode": "vault_only"})

    @app.post("/api/ui/vault/notes/{note_id}/ask-theseus/save", tags=["theseus-vault"])
    async def save_as_note(note_id: str, payload: SaveAsNoteRequest) -> JSONResponse:
        """Save an Ask Theseus answer as a new vault insight note."""
        source_note = vault_store.read(note_id)  # raises 404 if missing
        source_title = payload.source_title or source_note.get("title") or "Unknown"
        body = f"*Source: [[{source_title}]]*\n\n{payload.answer}"
        new_note = vault_store.create(
            title=f"Ask Theseus: {source_title[:60]}",
            body=body,
            note_type="insight",
            topic="",
            source="ask_theseus",
        )
        return JSONResponse(new_note, status_code=201)

    # ---------------------------------------------------------------------------
    # Knowledge Linker
    # ---------------------------------------------------------------------------

    @app.get("/api/ui/vault/recommend", tags=["theseus-vault"])
    async def recommend_notes(
        workspace: str | None = None,
        limit: int = 5,
    ) -> JSONResponse:
        """Return vault notes ranked by semantic overlap with workspace entities.

        When *workspace* is not supplied or *entities_func* is not configured,
        returns an empty list (graceful degradation).
        """
        if not workspace or entities_func is None:
            return JSONResponse({"recommendations": []})

        try:
            entity_terms: list[str] = await entities_func(workspace)
        except Exception:
            logger.exception("entities_func failed for workspace %s", workspace)
            return JSONResponse({"recommendations": []})

        if not entity_terms:
            return JSONResponse({"recommendations": []})

        notes = vault_store.list_notes()
        scored: list[tuple[float, dict]] = []
        for note in notes:
            score = _score_note(note, entity_terms)
            if score > 0:
                scored.append((score, note))

        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[:max(1, limit)]

        recommendations = []
        for score, note in top:
            body = note.get("body") or ""
            excerpt = (body[:120] + "…") if len(body) > 120 else body
            recommendations.append({
                "id": note["id"],
                "title": note.get("title", ""),
                "type": note.get("type", "raw"),
                "status": note.get("status", "raw"),
                "excerpt": excerpt,
                "score": score,
            })

        return JSONResponse({"recommendations": recommendations})

    @app.post("/api/ui/vault/notes/{note_id}/feed", tags=["theseus-vault"])
    async def feed_to_workspace(note_id: str, payload: FeedToWorkspaceRequest) -> JSONResponse:
        """Associate a vault note with a workspace by setting its pursuit field."""
        vault_store.read(note_id)  # raises 404 if missing
        updated = vault_store.update(note_id, pursuit=payload.workspace)
        return JSONResponse(updated)

    @app.post("/api/ui/vault/notes/{note_id}/extract-entities", tags=["theseus-vault"])
    async def extract_entities(
        note_id: str,
        payload: ExtractEntitiesRequest = None,
    ) -> JSONResponse:
        """Extract govcon entities from a vault note body.

        Returns a list of EntityProposal with entity_text, entity_type,
        confidence, and already_in_kg (checked against active workspace KG
        when workspace is provided).
        """
        if vault_curation_func is None:
            raise HTTPException(status_code=503, detail="Entity extraction LLM not configured")

        note = vault_store.read(note_id)  # raises 404 if missing
        body = note.get("body", "")

        from src.server.vault_llm import extract_entities_from_note

        proposals = await extract_entities_from_note(body, llm_func=vault_curation_func)

        workspace = (payload.workspace if payload else None) or None
        known_entities: set[str] = set()
        if workspace and entities_func is not None:
            try:
                terms: list[str] = await entities_func(workspace)
                known_entities = {t.lower() for t in terms}
            except Exception:
                logger.exception("entities_func failed for workspace %s", workspace)

        result = []
        for p in proposals:
            result.append({
                "entity_text": p.entity_text,
                "entity_type": p.entity_type,
                "confidence": p.confidence,
                "already_in_kg": p.entity_text.lower() in known_entities,
            })

        return JSONResponse({"proposals": result})

    @app.post("/api/ui/vault/notes/{note_id}/accept-entities", tags=["theseus-vault"])
    async def accept_entities(
        note_id: str,
        payload: AcceptEntitiesRequest,
    ) -> JSONResponse:
        """Commit accepted entity proposals to the active workspace KG.

        Returns 400 if no workspace is provided.
        Returns 503 if no KG insert function is configured.
        """
        if not payload.workspace:
            raise HTTPException(status_code=400, detail="workspace is required to commit entities to KG")
        if kg_insert_func is None:
            raise HTTPException(status_code=503, detail="KG insert function not configured")

        vault_store.read(note_id)  # raises 404 if missing

        entities_payload = [
            {
                "entity_text": p.entity_text,
                "entity_type": p.entity_type,
                "confidence": p.confidence,
            }
            for p in payload.proposals
        ]
        await kg_insert_func(payload.workspace, entities_payload)

        return JSONResponse({"accepted": len(payload.proposals), "workspace": payload.workspace})

    # ---------------------------------------------------------------------------
    # Graph view — nodes + edges for force-directed visualization
    # ---------------------------------------------------------------------------

    import re as _re

    _WIKILINK_RE = _re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*)?\]\]")

    @app.get("/api/ui/vault/graph", tags=["theseus-vault"])
    async def vault_graph(tier: str | None = None) -> JSONResponse:
        """Return all notes as nodes + wikilink/topic edges for graph visualization.

        Each node: {id, title, type, status, tier, topic, group}
        Each link: {source, target, kind}  (kind: wikilink | topic | pursuit)
        """
        all_notes = vault_store.list_notes()
        if tier:
            scoped = [n for n in all_notes if n.get("tier") == tier]
        else:
            scoped = all_notes

        id_set = {n["id"] for n in all_notes}
        slug_by_title: dict[str, str] = {
            (n.get("title") or "").lower(): n["id"]
            for n in all_notes if n.get("title")
        }

        nodes = []
        links = []
        topic_leaders: dict[str, str] = {}

        for n in scoped:
            nid = n["id"]
            topic = n.get("topic") or ""
            nodes.append({
                "id": nid,
                "title": n.get("title") or nid,
                "type": n.get("type") or "raw",
                "status": n.get("status") or "raw",
                "tier": n.get("tier") or "",
                "topic": topic,
                "pursuit": n.get("pursuit") or "",
            })
            # Wikilink edges from body
            body = n.get("body") or ""
            for match in _WIKILINK_RE.finditer(body):
                target_title = match.group(1).strip().lower()
                target_id = slug_by_title.get(target_title)
                if target_id and target_id != nid and target_id in id_set:
                    links.append({"source": nid, "target": target_id, "kind": "wikilink"})
            # Topic-cluster edges (connect to first note in same topic)
            if topic:
                if topic not in topic_leaders:
                    topic_leaders[topic] = nid
                elif topic_leaders[topic] != nid:
                    links.append({"source": topic_leaders[topic], "target": nid, "kind": "topic"})

        # Deduplicate links
        seen: set[tuple] = set()
        unique_links = []
        for lnk in links:
            key = (lnk["source"], lnk["target"], lnk["kind"])
            if key not in seen:
                seen.add(key)
                unique_links.append(lnk)

        return JSONResponse({"nodes": nodes, "links": unique_links})

