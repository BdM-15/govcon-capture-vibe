"""TDD contract tests for the Vault intel-feed tab (slice 4).

- $watch("vaultTab") in theseusInit triggers loadIntel when intel-feed activates
- Intel-feed tab HTML replaced with live summary (gaps + uncovered count + drill-through)
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).parent.parent
_CORE = _ROOT / "src" / "ui" / "static" / "app" / "theseus-core-helpers.js"
_INDEX = _ROOT / "src" / "ui" / "static" / "index.html"


# ── watcher setup ─────────────────────────────────────────────────────────────

def test_vault_intel_feed_init_watches_vault_tab() -> None:
    """theseusInit must register a $watch on vaultTab."""
    js = _CORE.read_text(encoding="utf-8")
    fn_start = js.find("window.theseusInit")
    assert fn_start != -1, "theseusInit not found"
    body = js[fn_start:]
    assert 'vaultTab' in body and '$watch' in body, (
        "theseusInit must $watch('vaultTab', ...) to react to tab changes"
    )


def test_vault_intel_feed_watch_calls_load_intel() -> None:
    """The vaultTab watcher must call loadIntel when intel-feed activates."""
    js = _CORE.read_text(encoding="utf-8")
    fn_start = js.find("window.theseusInit")
    body = js[fn_start:]
    assert "intel-feed" in body and "loadIntel" in body, (
        "vaultTab watcher must call loadIntel for the intel-feed tab"
    )


# ── HTML tab content ──────────────────────────────────────────────────────────

def test_vault_intel_tab_shows_loading_state() -> None:
    """Intel-feed tab must show a loading indicator while intel.loading is true."""
    html = _INDEX.read_text(encoding="utf-8")
    assert "intel.loading" in html, (
        "Intel-feed tab must reference intel.loading for its loading state"
    )


def test_vault_intel_tab_uses_intel_data() -> None:
    """Intel-feed tab must render content from intel.data."""
    html = _INDEX.read_text(encoding="utf-8")
    assert "intel.data" in html, (
        "Intel-feed tab must reference intel.data to display intelligence"
    )


def test_vault_intel_tab_shows_gaps() -> None:
    """Intel-feed tab now shows Zettelkasten swimlanes (Fleeting/Developing/Connected) — #147."""
    html = _INDEX.read_text(encoding="utf-8")
    assert "Fleeting" in html and "Developing" in html and "Connected" in html, (
        "Intel-feed tab must show Zettelkasten swimlane headings (Fleeting, Developing, Connected)"
    )


def test_vault_intel_tab_has_drill_through() -> None:
    """Intel-feed tab must have a link/button to navigate to the full intel view."""
    html = _INDEX.read_text(encoding="utf-8")
    # Matches active='intel', active = 'intel', active="intel", active = "intel"
    import re
    assert re.search(r"""active\s*=\s*['"]intel['"]""", html), (
        "Intel-feed tab must have a drill-through to the full intel view (active='intel')"
    )
