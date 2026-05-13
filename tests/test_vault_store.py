"""Tests for VaultStore — pure file I/O for Knowledge Vault notes."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from src.server.vault_store import VaultStore


def _store(tmp_path: Path) -> VaultStore:
    vault = tmp_path / "knowledge"
    vault.mkdir()
    return VaultStore(vault_dir=vault, now=lambda: "2026-05-13T10:00:00")


# ---------------------------------------------------------------------------
# Tracer bullet: create -> read roundtrip
# ---------------------------------------------------------------------------


def test_create_then_read_returns_same_note(tmp_path: Path) -> None:
    store = _store(tmp_path)

    note = store.create(
        title="My Capture Note",
        body="Some useful content here.",
        note_type="lesson_learned",
        topic="pricing",
        source="manual",
    )

    note_id = note["id"]
    assert note_id  # non-empty

    loaded = store.read(note_id)
    assert loaded["title"] == "My Capture Note"
    assert loaded["body"] == "Some useful content here."
    assert loaded["id"] == note_id


# ---------------------------------------------------------------------------
# Frontmatter completeness
# ---------------------------------------------------------------------------


def test_created_note_has_required_frontmatter_fields(tmp_path: Path) -> None:
    store = _store(tmp_path)
    note = store.create(
        title="Frontmatter Check",
        body="body text",
        note_type="raw_idea",
        topic="capture",
        source="manual",
    )

    assert note["type"] == "raw_idea"
    assert note["status"] == "raw"
    assert note["created"] == "2026-05-13T10:00:00"
    assert note["updated"] == "2026-05-13T10:00:00"
    assert note["topic"] == "capture"
    assert note["source"] == "manual"


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_list_notes_returns_one_entry_per_file(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create(title="Note A", body="a", note_type="raw_idea", topic="t", source="manual")
    store.create(title="Note B", body="b", note_type="capability", topic="t", source="manual")

    notes = store.list_notes()
    assert len(notes) == 2
    titles = {n["title"] for n in notes}
    assert titles == {"Note A", "Note B"}


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_update_patches_title_and_bumps_updated(tmp_path: Path) -> None:
    _now_calls = iter(["2026-05-13T10:00:00", "2026-05-13T11:00:00"])
    vault = tmp_path / "knowledge"
    vault.mkdir()
    store = VaultStore(vault_dir=vault, now=lambda: next(_now_calls))

    note = store.create(title="Old Title", body="body", note_type="raw_idea", topic="t", source="manual")
    note_id = note["id"]

    updated = store.update(note_id, title="New Title")
    assert updated["title"] == "New Title"
    assert updated["updated"] == "2026-05-13T11:00:00"
    assert updated["created"] == "2026-05-13T10:00:00"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_removes_file_and_read_raises_404(tmp_path: Path) -> None:
    store = _store(tmp_path)
    note = store.create(title="Temporary", body="x", note_type="raw_idea", topic="t", source="manual")
    note_id = note["id"]

    store.delete(note_id)

    with pytest.raises(HTTPException) as exc_info:
        store.read(note_id)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Path traversal guard (OWASP A01)
# ---------------------------------------------------------------------------


def test_path_traversal_raises_400(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        store.path("../etc/passwd")
    assert exc_info.value.status_code == 400


def test_path_traversal_with_encoded_dots_raises_400(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        store.path("..%2Fetc%2Fpasswd")
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# ID collision — same title produces distinct IDs
# ---------------------------------------------------------------------------


def test_id_collision_produces_distinct_ids(tmp_path: Path) -> None:
    store = _store(tmp_path)
    a = store.create(title="Same Title", body="a", note_type="raw_idea", topic="t", source="manual")
    b = store.create(title="Same Title", body="b", note_type="raw_idea", topic="t", source="manual")

    assert a["id"] != b["id"]
    assert store.read(a["id"])["body"] == "a"
    assert store.read(b["id"])["body"] == "b"
