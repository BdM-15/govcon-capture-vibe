"""
VaultStore — file-based persistence for Knowledge Vault notes.

Each note is a Markdown file with YAML frontmatter stored under
``vault_dir/<id>.md``.  Mirrors the ChatStore pattern: pure file I/O,
injectable ``now`` callable so tests can control timestamps.

Frontmatter schema (Obsidian-compatible):
    type:       lesson_learned | capability | customer_intel | article |
                training | raw_idea | conference_note | shipley_ref
    status:     raw | polished | evergreen
    title:      str
    topic:      str
    source:     str  (URL, filename, or "manual")
    pursuit:    str  (optional workspace name)
    promoted_to: list[str] (workspace names or "evergreen")
    tags:       list[str]
    created:    ISO datetime
    updated:    ISO datetime
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

# yaml is part of the stdlib-level PyYAML package already declared as a dep
import yaml

logger = __import__("logging").getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_DEFAULT_STATUS = "raw"


def _slugify(text: str) -> str:
    """Lower-case alphanumeric slug, hyphens for runs of other chars."""
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug or "note"


def _parse_note_file(path: Path, note_id: str) -> dict[str, Any]:
    """Parse ``<id>.md`` into a dict with ``id`` and ``body`` keys."""
    raw = path.read_text(encoding="utf-8")
    if raw.startswith("---"):
        # Split on the closing ---
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            fm = yaml.safe_load(parts[1]) or {}
            body = parts[2].lstrip("\n")
        else:
            fm = {}
            body = raw
    else:
        fm = {}
        body = raw
    fm["id"] = note_id
    fm["body"] = body
    return fm


def _render_note_file(fields: dict[str, Any], body: str) -> str:
    """Serialize frontmatter + body to Markdown string."""
    fm_fields = {
        k: v
        for k, v in fields.items()
        if k not in ("id", "body")
    }
    fm_yaml = yaml.dump(fm_fields, allow_unicode=True, sort_keys=True, default_flow_style=False)
    return f"---\n{fm_yaml}---\n\n{body}"


class VaultStore:
    """
    Knowledge Vault note persistence.

    Parameters
    ----------
    vault_dir:
        Directory where ``.md`` files are stored (one file per note).
    now:
        Callable returning an ISO datetime string used for ``created`` /
        ``updated`` timestamps.  Injectable for test determinism.
    """

    def __init__(self, vault_dir: Path, now: Callable[[], str]) -> None:
        self._dir = vault_dir
        self._now = now

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def path(self, note_id: str) -> Path:
        """Return the filesystem path for *note_id*, rejecting traversal attempts."""
        # Reject percent-encoded sequences before resolution
        if "%" in note_id or "\\" in note_id:
            raise HTTPException(status_code=400, detail="Invalid note id")
        candidate = (self._dir / f"{note_id}.md").resolve()
        try:
            candidate.relative_to(self._dir.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid note id")
        return candidate

    def create(
        self,
        *,
        title: str,
        body: str,
        note_type: str,
        topic: str,
        source: str,
        pursuit: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new note and return its full dict representation."""
        note_id = self._unique_id(title)
        now = self._now()
        fields: dict[str, Any] = {
            "title": title,
            "type": note_type,
            "status": _DEFAULT_STATUS,
            "topic": topic,
            "source": source,
            "pursuit": pursuit,
            "promoted_to": [],
            "tags": tags or [],
            "created": now,
            "updated": now,
        }
        content = _render_note_file(fields, body)
        file_path = self._dir / f"{note_id}.md"
        file_path.write_text(content, encoding="utf-8")
        return {**fields, "id": note_id, "body": body}

    def read(self, note_id: str) -> dict[str, Any]:
        """Return note dict or raise 404."""
        file_path = self.path(note_id)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Note '{note_id}' not found")
        return _parse_note_file(file_path, note_id)

    def update(self, note_id: str, **fields: Any) -> dict[str, Any]:
        """Patch *fields* on an existing note; bump ``updated``. Return updated dict."""
        note = self.read(note_id)
        body = fields.pop("body", note["body"])
        note.update(fields)
        note["updated"] = self._now()
        content = _render_note_file(note, body)
        self.path(note_id).write_text(content, encoding="utf-8")
        return {**note, "body": body}

    def delete(self, note_id: str) -> None:
        """Delete the note file or raise 404."""
        file_path = self.path(note_id)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Note '{note_id}' not found")
        file_path.unlink()

    def list_notes(self) -> list[dict[str, Any]]:
        """Return all notes sorted by ``updated`` descending."""
        notes = []
        for md_file in self._dir.glob("*.md"):
            note_id = md_file.stem
            try:
                notes.append(_parse_note_file(md_file, note_id))
            except Exception:
                logger.warning("Skipping unreadable vault note: %s", md_file)
        notes.sort(key=lambda n: n.get("updated", ""), reverse=True)
        return notes

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _unique_id(self, title: str) -> str:
        """Slugify *title*; append ``--2``, ``--3`` etc. on collision."""
        base = _slugify(title)
        candidate = base
        counter = 2
        while (self._dir / f"{candidate}.md").exists():
            candidate = f"{base}--{counter}"
            counter += 1
        return candidate
