"""Tests for #138 — KNOWLEDGE nav group + Quick-Capture FAB."""
from __future__ import annotations

import json
import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_CONSTANTS = _ROOT / "src" / "ui" / "static" / "app" / "theseus-constants.js"
_STATE = _ROOT / "src" / "ui" / "static" / "app" / "theseus-state-helpers.js"
_INDEX = _ROOT / "src" / "ui" / "static" / "index.html"
_CSS = _ROOT / "src" / "ui" / "static" / "styles" / "theseus.css"


# ── nav group helpers ──────────────────────────────────────────────────────────

def _parse_nav_groups(js: str) -> list[dict]:
    """Extract the returned array literal from createTheseusNavGroups()."""
    # Pull the return [...] block by balanced-bracket walking
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
    # Normalise JS object literals to JSON by quoting bare keys, removing
    # trailing commas, and stripping single-line comments.
    raw = re.sub(r"//[^\n]*", "", raw)                  # strip // comments
    raw = re.sub(r",\s*([}\]])", r"\1", raw)             # trailing commas
    raw = re.sub(r"([{,]\s*)(\w+)(\s*:)", r'\1"\2"\3', raw)  # bare keys → "key"
    return json.loads(raw)


# ── Tracer bullet ─────────────────────────────────────────────────────────────

def test_knowledge_nav_group_exists() -> None:
    """KNOWLEDGE group must be present in createTheseusNavGroups()."""
    js = _CONSTANTS.read_text(encoding="utf-8")
    groups = _parse_nav_groups(js)
    ids = [g["id"] for g in groups]
    assert "knowledge" in ids, f"No 'knowledge' group found; groups: {ids}"


# ── Nav group structure ───────────────────────────────────────────────────────

def test_knowledge_group_has_vault_and_intel_feed_items() -> None:
    js = _CONSTANTS.read_text(encoding="utf-8")
    groups = _parse_nav_groups(js)
    kg = next(g for g in groups if g["id"] == "knowledge")
    item_ids = [i["id"] for i in kg["items"]]
    assert "vault" in item_ids
    assert "intel-feed" in item_ids


def test_knowledge_group_vault_item_spec() -> None:
    js = _CONSTANTS.read_text(encoding="utf-8")
    groups = _parse_nav_groups(js)
    kg = next(g for g in groups if g["id"] == "knowledge")
    vault = next(i for i in kg["items"] if i["id"] == "vault")
    assert vault["icon"] == "book-open"
    assert vault["accent"] == "lime"


def test_knowledge_group_intel_feed_item_spec() -> None:
    js = _CONSTANTS.read_text(encoding="utf-8")
    groups = _parse_nav_groups(js)
    kg = next(g for g in groups if g["id"] == "knowledge")
    feed = next(i for i in kg["items"] if i["id"] == "intel-feed")
    assert feed["icon"] == "inbox"
    assert feed["accent"] == "amber"


def test_knowledge_group_between_tools_and_system() -> None:
    js = _CONSTANTS.read_text(encoding="utf-8")
    groups = _parse_nav_groups(js)
    ids = [g["id"] for g in groups]
    assert "tools" in ids and "knowledge" in ids and "system" in ids
    tools_idx = ids.index("tools")
    knowledge_idx = ids.index("knowledge")
    system_idx = ids.index("system")
    assert tools_idx < knowledge_idx < system_idx, (
        f"Expected tools({tools_idx}) < knowledge({knowledge_idx}) < system({system_idx})"
    )


# ── Quick-Capture FAB — markup ────────────────────────────────────────────────

def test_fab_element_present_in_index_html() -> None:
    html = _INDEX.read_text(encoding="utf-8")
    assert "quick-capture-fab" in html, "FAB element with class 'quick-capture-fab' not found in index.html"


def test_fab_opens_quick_capture_modal() -> None:
    html = _INDEX.read_text(encoding="utf-8")
    # The FAB button must trigger quickCapture.open = true (or equivalent)
    assert "quickCapture" in html, "No quickCapture Alpine binding found in index.html"


def test_fab_modal_has_title_body_type_fields() -> None:
    html = _INDEX.read_text(encoding="utf-8")
    assert "quickCapture.title" in html, "Missing title field binding"
    assert "quickCapture.body" in html, "Missing body field binding"
    assert "quickCapture.type" in html, "Missing type field binding"


# ── Quick-Capture FAB — state ─────────────────────────────────────────────────

def test_quick_capture_state_initialized_in_state_helpers() -> None:
    js = _STATE.read_text(encoding="utf-8")
    assert "quickCapture" in js, "quickCapture state not initialized in theseus-state-helpers.js"


# ── CSS ───────────────────────────────────────────────────────────────────────

def test_fab_css_class_defined() -> None:
    css = _CSS.read_text(encoding="utf-8")
    assert ".quick-capture-fab" in css, ".quick-capture-fab CSS class not defined"


def test_fab_modal_css_class_defined() -> None:
    css = _CSS.read_text(encoding="utf-8")
    assert ".quick-capture-modal" in css, ".quick-capture-modal CSS class not defined"
