"""Agnostic external web search and crawl infrastructure for Theseus."""

from __future__ import annotations

from src.web_research.service import (
    fetch_page,
    provider_status,
    research,
    search_web,
)

__all__ = [
    "fetch_page",
    "provider_status",
    "research",
    "search_web",
]