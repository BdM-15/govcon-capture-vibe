"""Vault capture orchestrator.

One deep entry point that takes a raw capture body, runs the vault-curation
LLM (classify + polish in one round-trip), suggests wikilinks against the
vault index, persists the note via VaultStore, and returns a typed result.

This module owns the orchestration only — classification/polish prompt rules
live in ``vault_llm.py``; persistence rules live in ``vault_store.py``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from src.server.vault_llm import polish_note
from src.server.vault_store import VaultStore

logger = logging.getLogger(__name__)


@dataclass
class CapturedNote:
    """Result of a single capture invocation."""
    note_id: str
    note_type: str
    title: str
    raw_body: str
    polished_body: str
    auto_polished: bool
    wikilink_suggestions: list[str]
    path: Path


async def capture(
    raw_body: str,
    *,
    llm_func: Callable[..., Awaitable[str]],
    vault_store: VaultStore,
    vault_index: dict[str, str],
    auto_polish: bool,
) -> CapturedNote:
    """Capture a raw idea into a persisted, classified, optionally polished note.

    Args:
        raw_body: Free-form text from the user's capture stream.
        llm_func: Async ``(prompt, system_prompt=...) -> str`` returning a
            TYPE/TITLE/BODY response (matches ``vault_llm.polish_note`` contract).
        vault_store: VaultStore for persistence.
        vault_index: title -> slug mapping for wikilink scoring.
        auto_polish: If True, invoke the LLM to classify+polish; if False,
            persist as-is with type "raw" and a heuristic title.

    Returns:
        CapturedNote with classification, polished body, wikilink suggestions,
        and the on-disk path.
    """
    if not raw_body or not raw_body.strip():
        raise ValueError("Capture body is empty")

    if auto_polish:
        try:
            result = await polish_note(
                raw_body=raw_body,
                note_type="raw",
                model_role="vault_curation",
                vault_index=vault_index,
                llm_func=llm_func,
            )
            title = result.title
            note_type = result.note_type
            body = result.rewritten
            suggestions = result.wikilink_suggestions
            polished = True
        except Exception:  # noqa: BLE001 — degrade gracefully, log + persist raw
            logger.exception("Vault capture polish failed; falling back to raw note")
            title = _heuristic_title(raw_body)
            note_type = "raw"
            body = raw_body
            suggestions = []
            polished = False
    else:
        title = _heuristic_title(raw_body)
        note_type = "raw"
        body = raw_body
        suggestions = []
        polished = False

    persisted: dict[str, Any] = vault_store.create(
        title=title,
        body=body,
        note_type=note_type,
        topic="",
        source="capture",
    )

    return CapturedNote(
        note_id=persisted["id"],
        note_type=note_type,
        title=title,
        raw_body=raw_body,
        polished_body=body,
        auto_polished=polished,
        wikilink_suggestions=suggestions,
        path=vault_store.path(persisted["id"]),
    )


def _heuristic_title(raw_body: str) -> str:
    """Cheap title fallback when no LLM call is made."""
    text = raw_body.strip().splitlines()[0] if raw_body.strip() else "untitled"
    return (text[:60] + "…") if len(text) > 60 else text
