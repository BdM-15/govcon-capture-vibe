"""vault_llm — ontology-aware LLM intelligence layer for the Knowledge Vault.

Pure async functions; no web-framework dependency. Independently testable.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class PolishResult:
    """Output of `polish_note`."""
    original: str
    rewritten: str
    diff_hunks: list[str]
    wikilink_suggestions: list[str]
    title: str = field(default="")
    note_type: str = field(default="raw")


@dataclass
class EntityProposal:
    """Structured entity proposal extracted from a note (stub for #146)."""
    name: str
    entity_type: str


# ---------------------------------------------------------------------------
# Polish prompt
# ---------------------------------------------------------------------------

def _build_polish_system_prompt() -> str:
    """Build an ontology-aware system prompt for note polishing.

    Inlines the core govcon entity types and relationship types so the model
    can suggest govcon vocabulary and wikilink targets aligned with the
    Theseus ontology.
    """
    from src.ontology.schema import VALID_ENTITY_TYPES, VALID_RELATIONSHIP_TYPES

    entity_list = ", ".join(sorted(VALID_ENTITY_TYPES))
    rel_list = ", ".join(sorted(VALID_RELATIONSHIP_TYPES))

    return (
        "You are a govcon capture analyst and Obsidian Markdown expert. "
        "Rewrite the note below into clean, atomic, wikilink-ready Markdown.\n\n"
        "Rules (Obsidian markdown style):\n"
        "- Keep ideas atomic: one idea per note where possible\n"
        "- Use [[wikilink]] syntax for concepts that deserve their own note\n"
        "- Use #tags sparingly for cross-cutting themes\n"
        "- Use ## headings for structure in longer notes\n"
        "- Preserve all factual content; do not hallucinate\n\n"
        f"Govcon entity types to recognise: {entity_list}\n\n"
        f"Canonical relationship types: {rel_list}\n\n"
        "Return EXACTLY:\n"
        "TYPE: <insight|action|risk|theme|question|raw>\n"
        "TITLE: <concise title max 80 chars>\n"
        "BODY: <polished Markdown body>\n"
        "No extra text before TYPE: or after the BODY content."
    )


_POLISH_PROMPT_TEMPLATE = "Polish this govcon capture note:\n\n{body}"

_VALID_NOTE_TYPES = frozenset({"insight", "action", "risk", "theme", "question", "raw"})


def _parse_llm_response(raw: str, fallback_body: str) -> tuple[str, str, str]:
    """Extract (title, note_type, body) from a TYPE:/TITLE:/BODY: response."""
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

    # Legacy fallback
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
        title = (words[:60] + "…") if len(words) > 60 else words
    return title, note_type, body


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------


def _compute_diff_hunks(original: str, rewritten: str) -> list[str]:
    """Return unified diff lines between original and rewritten."""
    orig_lines = original.splitlines(keepends=True)
    new_lines = rewritten.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(orig_lines, new_lines, fromfile="original", tofile="rewritten", lineterm="")
    )
    return [line.rstrip("\n") for line in diff]


# ---------------------------------------------------------------------------
# Wikilink suggestion
# ---------------------------------------------------------------------------


def _suggest_wikilinks(polished_body: str, vault_index: dict[str, str]) -> list[str]:
    """Return ``[[Title]]`` strings for vault notes whose titles appear in the body.

    A title is considered a match when at least half of its significant words
    (len > 3) appear in the polished body (case-insensitive).
    """
    body_lower = polished_body.lower()
    suggestions: list[str] = []
    for title in vault_index:
        words = [w for w in title.lower().split() if len(w) > 3]
        if not words:
            continue
        matches = sum(1 for w in words if w in body_lower)
        if matches >= max(1, len(words) // 2):
            suggestions.append(f"[[{title}]]")
    return suggestions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def polish_note(
    raw_body: str,
    note_type: str,
    model_role: str,
    vault_index: dict[str, str],
    llm_func: Callable[..., Any],
) -> PolishResult:
    """Polish a vault note body using the provided LLM function.

    Args:
        raw_body: Current note body text.
        note_type: Current note type (e.g. "raw", "insight").
        model_role: "vault_curation" or "query" — informational; caller selects llm_func.
        vault_index: title → slug mapping of all vault notes (for wikilink suggestions).
        llm_func: Async callable ``(prompt, system_prompt=...) -> str``.

    Returns:
        PolishResult with original, rewritten, diff_hunks, wikilink_suggestions.
    """
    system_prompt = _build_polish_system_prompt()
    prompt = _POLISH_PROMPT_TEMPLATE.format(body=raw_body.strip())
    raw_response = await llm_func(prompt, system_prompt=system_prompt)
    extracted_title, extracted_type, polished_body = _parse_llm_response(raw_response, fallback_body=raw_body)

    diff_hunks = _compute_diff_hunks(raw_body, polished_body)
    wikilink_suggestions = _suggest_wikilinks(polished_body, vault_index)

    return PolishResult(
        original=raw_body,
        rewritten=polished_body,
        diff_hunks=diff_hunks,
        wikilink_suggestions=wikilink_suggestions,
        title=extracted_title,
        note_type=extracted_type,
    )


async def extract_entities_from_note(body: str) -> list[EntityProposal]:
    """Extract govcon entities from a note body (stub — wired fully in #146).

    Returns:
        Empty list until #146 is implemented.
    """
    return []


async def ask_theseus_about_note(note_body: str, workspace: str) -> str:
    """Query the workspace KG using note body as context (stub — wired fully in #147).

    Returns:
        Empty string until #147 is implemented.
    """
    return ""
