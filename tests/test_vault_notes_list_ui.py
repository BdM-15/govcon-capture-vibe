"""TDD contract tests for the Vault Notes live list (slices 1 + 2).

Slice 1 — state + HTML binding:
  - vaultNotes array + vaultNotesLoading flag in Alpine state
  - Notes tab has x-for bound to vaultNotes

Slice 2 — load-on-activate wiring:
  - theseusHandleActiveChange fires loadVaultNotes when active === 'vault'
  - app-delegates exposes loadVaultNotes() method
  - theseus-vault-helpers.js module exists with theseusLoadVaultNotes fn
  - script tag wires vault-helpers into the page
  - HITL save success handler calls loadVaultNotes()
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_STATE = _ROOT / "src" / "ui" / "static" / "app" / "theseus-state-helpers.js"
_CORE = _ROOT / "src" / "ui" / "static" / "app" / "theseus-core-helpers.js"
_DELEGATES = _ROOT / "src" / "ui" / "static" / "app" / "theseus-app-delegates.js"
_VAULT_HELPERS = _ROOT / "src" / "ui" / "static" / "app" / "theseus-vault-helpers.js"
_INDEX = _ROOT / "src" / "ui" / "static" / "index.html"


# ── Slice 1: state ────────────────────────────────────────────────────────────

def test_vault_notes_state_has_notes_array() -> None:
    """vaultNotes initialised as empty array in Alpine state."""
    js = _STATE.read_text(encoding="utf-8")
    assert "vaultNotes:" in js, "vaultNotes array missing from Alpine initial state"


def test_vault_notes_state_has_loading_flag() -> None:
    """vaultNotesLoading initialised as false in Alpine state."""
    js = _STATE.read_text(encoding="utf-8")
    assert "vaultNotesLoading:" in js, "vaultNotesLoading flag missing from Alpine initial state"


# ── Slice 1: HTML binding ─────────────────────────────────────────────────────

def test_vault_notes_tab_has_x_for_binding() -> None:
    """Notes tab must iterate with x-for over vaultNotes."""
    html = _INDEX.read_text(encoding="utf-8")
    assert 'x-for="note in vaultNotes"' in html, (
        "Notes tab must have x-for=\"note in vaultNotes\" binding"
    )


def test_vault_notes_tab_renders_note_title() -> None:
    """Note cards must render the note title field."""
    html = _INDEX.read_text(encoding="utf-8")
    assert "note.title" in html, "Note card must display note.title"


def test_vault_notes_tab_renders_note_type() -> None:
    """Note cards must render the note type badge."""
    html = _INDEX.read_text(encoding="utf-8")
    assert "note.type" in html, "Note card must display note.type badge"


# ── Slice 2: core-helpers dispatch ───────────────────────────────────────────

def test_vault_notes_core_handler_triggers_load() -> None:
    """theseusHandleActiveChange must call loadVaultNotes when active === 'vault'."""
    js = _CORE.read_text(encoding="utf-8")
    assert "vault" in js and "loadVaultNotes" in js, (
        "theseusHandleActiveChange must have a vault branch calling loadVaultNotes"
    )


# ── Slice 2: delegates ────────────────────────────────────────────────────────

def test_vault_notes_delegates_has_load_method() -> None:
    """theseus-app-delegates.js must expose a loadVaultNotes() method."""
    js = _DELEGATES.read_text(encoding="utf-8")
    assert "loadVaultNotes" in js, "app-delegates must have loadVaultNotes method"


# ── Slice 2: helper module ────────────────────────────────────────────────────

def test_vault_notes_helper_file_exists() -> None:
    """theseus-vault-helpers.js must exist."""
    assert _VAULT_HELPERS.exists(), "theseus-vault-helpers.js not found"


def test_vault_notes_helper_fn_defined() -> None:
    """vault-helpers.js must define window.theseusLoadVaultNotes."""
    js = _VAULT_HELPERS.read_text(encoding="utf-8")
    assert "theseusLoadVaultNotes" in js, (
        "theseus-vault-helpers.js must define window.theseusLoadVaultNotes"
    )


def test_vault_notes_helper_fetches_endpoint() -> None:
    """vault-helpers.js must fetch /api/ui/vault/notes."""
    js = _VAULT_HELPERS.read_text(encoding="utf-8")
    assert "/api/ui/vault/notes" in js, (
        "theseusLoadVaultNotes must fetch /api/ui/vault/notes"
    )


# ── Slice 2: script tag ───────────────────────────────────────────────────────

def test_vault_notes_script_tag_in_html() -> None:
    """index.html must load theseus-vault-helpers.js."""
    html = _INDEX.read_text(encoding="utf-8")
    assert "theseus-vault-helpers.js" in html, (
        "index.html must have a <script src> for theseus-vault-helpers.js"
    )


# ── Slice 2: reload after HITL save ──────────────────────────────────────────

def test_vault_notes_reload_after_hitl_save() -> None:
    """HITL save success handler must call loadVaultNotes() to refresh the list."""
    html = _INDEX.read_text(encoding="utf-8")
    assert "loadVaultNotes" in html, (
        "HITL save success handler must call loadVaultNotes() to refresh the notes list"
    )


# ── Slice 3: delete button ────────────────────────────────────────────────────

def test_vault_notes_delete_fn_in_helpers() -> None:
    """vault-helpers.js must define window.theseusDeleteVaultNote."""
    js = _VAULT_HELPERS.read_text(encoding="utf-8")
    assert "theseusDeleteVaultNote" in js, (
        "theseus-vault-helpers.js must define window.theseusDeleteVaultNote"
    )


def test_vault_notes_delete_calls_endpoint() -> None:
    """theseusDeleteVaultNote must call the DELETE endpoint."""
    js = _VAULT_HELPERS.read_text(encoding="utf-8")
    assert "DELETE" in js and "/api/ui/vault/notes/" in js, (
        "theseusDeleteVaultNote must call DELETE /api/ui/vault/notes/{id}"
    )


def test_vault_notes_delete_refreshes_list() -> None:
    """theseusDeleteVaultNote must reload the notes list after deletion."""
    js = _VAULT_HELPERS.read_text(encoding="utf-8")
    fn_marker = "async function theseusDeleteVaultNote"
    idx = js.find(fn_marker)
    assert idx != -1, "theseusDeleteVaultNote function not found"
    body = js[idx:]
    assert "theseusLoadVaultNotes" in body, (
        "theseusDeleteVaultNote must call theseusLoadVaultNotes to refresh"
    )


def test_vault_notes_delegates_has_delete_method() -> None:
    """theseus-app-delegates.js must expose a deleteVaultNote() method."""
    js = _DELEGATES.read_text(encoding="utf-8")
    assert "deleteVaultNote" in js, "app-delegates must have deleteVaultNote method"


def test_vault_notes_card_has_delete_button() -> None:
    """Each note card must have a delete button calling deleteVaultNote."""
    html = _INDEX.read_text(encoding="utf-8")
    assert "deleteVaultNote" in html, (
        "Note card must have a delete button that calls deleteVaultNote"
    )
