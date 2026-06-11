"""Lightweight HTML-to-text helpers for direct fetch fallback."""

from __future__ import annotations

import re


_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_WS_RE = re.compile(r"\s+")


def html_to_text(html: str) -> str:
    """Strip tags and collapse whitespace from raw HTML."""
    if not html:
        return ""
    cleaned = _SCRIPT_STYLE_RE.sub(" ", html)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("&nbsp;", " ").replace("&amp;", "&")
    cleaned = _WS_RE.sub(" ", cleaned)
    return cleaned.strip()