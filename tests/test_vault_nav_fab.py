"""Tests for vault nav + Quick-Capture FAB design (redesign from #138).

Design decisions encoded here:
- Vault lives under CAPTURE nav group (same mental mode as Studio)
- No standalone KNOWLEDGE nav group
- Intel Feed is a tab inside the Vault page, not a separate nav destination
- FAB modal = brain-dump only (title + body); AI infers type in background
- quickCapture state has no user-facing type field
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_CONSTANTS = _ROOT / "src" / "ui" / "static" / "app" / "theseus-constants.js"
_STATE = _ROOT / "src" / "ui" / "static" / "app" / "theseus-state-helpers.js"
_INDEX = _ROOT / "src" / "ui" / "static" / "index.html"
_CSS = _ROOT / "src" / "ui" / "static" / "styles" / "theseus.css"


# ── nav group parser ───────────────────────────────────────────────────────────

def _parse_nav_groups(js: str) -> list[dict]:
    """Extract the returned array literal from createTheseusNavGroups()."""
    match = re.search(r"return\s*(\[)", js)
    assert match, "No return [...] found in createTheseusNavGroups"
    start = match.start(1)
    depth = 0
    for i, ch in enumerate(js[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                raw = js[start : i + 1]
                break
    raw = re.sub(r"//[^\n]*", "", raw)
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    raw = re.sub(r"([{,]\s*)(\w+)(\s*:)", r'\1"\2"\3', raw)
    return json.loads(raw)


def _all_item_ids(groups: list[dict]) -> list[str]:
    return [item["id"] for g in groups for item in g.get("items", [])]


# ── Tracer bullet: vault in CAPTURE ──────────────────────────────────────────

def test_vault_item_exists_in_capture_group() -> None:
    """Vault must be a nav item inside the CAPTURE group."""
    js = _CONSTANTS.read_text(encoding="utf-8")
    groups = _parse_nav_groups(js)
    capture = next((g for g in groups if g["id"] == "capture"), None)
    assert capture is not None, "No 'capture' group found"
    item_ids = [i["id"] for i in capture["items"]]
    assert "vault" in item_ids, f"'vault' not in CAPTURE items: {item_ids}"


# ── Nav group structure ───────────────────────────────────────────────────────

def test_no_knowledge_nav_group() -> None:
    """KNOWLEDGE group must not exist — vault belongs to CAPTURE."""
    js = _CONSTANTS.read_text(encoding="utf-8")
    groups = _parse_nav_groups(js)
    ids = [g["id"] for g in groups]
    assert "knowledge" not in ids, (
        "Found unexpected 'knowledge' nav group — vault should live under CAPTURE"
    )


def test_no_intel_feed_nav_item() -> None:
    """intel-feed must not be a top-level nav item — it's a tab inside Vault."""
    js = _CONSTANTS.read_text(encoding="utf-8")
    groups = _parse_nav_groups(js)
    all_ids = _all_item_ids(groups)
    assert "intel-feed" not in all_ids, (
        "'intel-feed' should be a tab inside the Vault panel, not a nav item"
    )


def test_vault_item_spec() -> None:
    """Vault nav item must use book-open icon and lime accent."""
    js = _CONSTANTS.read_text(encoding="utf-8")
    groups = _parse_nav_groups(js)
    capture = next(g for g in groups if g["id"] == "capture")
    vault = next(i for i in capture["items"] if i["id"] == "vault")
    assert vault["icon"] == "book-open"
    assert vault["accent"] == "lime"


def test_vault_after_studio_in_capture() -> None:
    """Vault must appear after Studio in CAPTURE — same capture workflow order."""
    js = _CONSTANTS.read_text(encoding="utf-8")
    groups = _parse_nav_groups(js)
    capture = next(g for g in groups if g["id"] == "capture")
    item_ids = [i["id"] for i in capture["items"]]
    assert "studio" in item_ids and "vault" in item_ids
    assert item_ids.index("studio") < item_ids.index("vault"), (
        f"vault({item_ids.index('vault')}) should come after studio({item_ids.index('studio')})"
    )


# ── FAB — brain-dump UX (no type dropdown for user) ──────────────────────────

def test_fab_element_present_in_index_html() -> None:
    html = _INDEX.read_text(encoding="utf-8")
    assert "quick-capture-fab" in html


def test_fab_opens_quick_capture_modal() -> None:
    html = _INDEX.read_text(encoding="utf-8")
    assert "quickCapture.open" in html


def test_fab_modal_has_title_field() -> None:
    html = _INDEX.read_text(encoding="utf-8")
    assert "quickCapture.title" in html


def test_fab_modal_has_body_field() -> None:
    html = _INDEX.read_text(encoding="utf-8")
    assert "quickCapture.body" in html


def test_fab_modal_has_no_type_dropdown() -> None:
    """User should not see a type selector — AI infers it in the background."""
    html = _INDEX.read_text(encoding="utf-8")
    # There must be no <select> for type inside the quick-capture-modal.
    # We test for the absence of the explicit type-select binding from #138.
    assert 'x-model="quickCapture.type"' not in html, (
        "FAB modal must not expose a type dropdown — AI classifies automatically"
    )


# ── FAB — Alpine state ────────────────────────────────────────────────────────

def test_quick_capture_state_initialized() -> None:
    js = _STATE.read_text(encoding="utf-8")
    assert "quickCapture" in js


def test_quick_capture_state_has_no_user_type_field() -> None:
    """quickCapture state has no user-facing 'type' property (AI sets it)."""
    js = _STATE.read_text(encoding="utf-8")
    # Locate the quickCapture object block and assert 'type:' is absent within it
    match = re.search(r"quickCapture\s*:\s*\{([^}]+)\}", js, re.DOTALL)
    assert match, "quickCapture state block not found in theseus-state-helpers.js"
    block = match.group(1)
    assert "type:" not in block, (
        "quickCapture state must not expose a 'type' field — AI handles classification"
    )


# ── Vault panel — tabbed layout ───────────────────────────────────────────────

def test_vault_panel_has_notes_tab() -> None:
    html = _INDEX.read_text(encoding="utf-8")
    assert "vault-tab-notes" in html, "Vault panel must have a Notes tab (id/ref vault-tab-notes)"


def test_vault_panel_has_intel_feed_tab() -> None:
    html = _INDEX.read_text(encoding="utf-8")
    assert "vault-tab-intel" in html, "Vault panel must have an Intel Feed tab (id/ref vault-tab-intel)"


# ── CSS ───────────────────────────────────────────────────────────────────────

def test_fab_css_class_defined() -> None:
    css = _CSS.read_text(encoding="utf-8")
    assert ".quick-capture-fab" in css


def test_fab_modal_css_class_defined() -> None:
    css = _CSS.read_text(encoding="utf-8")
    assert ".quick-capture-modal" in css
