"""Tests for agnostic web research infrastructure."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.web_research.config import WebResearchSettings
from src.web_research.html import html_to_text
from src.web_research.service import fetch_page, provider_status, search_web


def _settings(**overrides) -> WebResearchSettings:
    base = {
        "serpapi_api_key": "",
        "olostep_api_key": "",
        "firecrawl_api_key": "",
        "searxng_base_url": "",
        "enabled": True,
        "enable_search": True,
        "enable_fetch": True,
        "enable_firecrawl": False,
        "enable_direct_fetch": True,
        "enable_crawl4ai": True,
        "fetch_timeout_seconds": 5.0,
        "max_content_chars": 500,
        "max_search_results": 5,
        "cache_ttl_seconds": 0,
        "cache_dir_name": "_web_research_cache",
    }
    base.update(overrides)
    return WebResearchSettings(**base)


def test_html_to_text_strips_tags() -> None:
    raw = "<html><body><script>ignore()</script><h1>Title</h1><p>Body</p></body></html>"
    assert "Title" in html_to_text(raw)
    assert "Body" in html_to_text(raw)
    assert "ignore" not in html_to_text(raw)


def test_provider_status_free_first() -> None:
    status = provider_status(_settings(serpapi_api_key="key", firecrawl_api_key="fc"))
    assert status["policy"]["search_order"] == ["searxng", "serpapi"]
    assert status["policy"]["fetch_standard_order"] == ["direct", "crawl4ai"]
    assert status["fetch"][-1]["id"] == "firecrawl"
    assert status["fetch"][-1]["enabled_in_chain"] is False


def test_provider_status_firecrawl_in_standard_chain_when_enabled() -> None:
    status = provider_status(
        _settings(firecrawl_api_key="fc", enable_firecrawl=True),
    )
    assert "firecrawl" in status["policy"]["fetch_standard_order"]


@pytest.mark.asyncio
async def test_search_web_prefers_searxng_hits() -> None:
    settings = _settings(searxng_base_url="http://localhost:8080", serpapi_api_key="serp")
    searx_hits = [
        {
            "title": "A",
            "url": "https://example.com/a",
            "snippet": "one",
            "provider": "searxng",
            "rank": 1,
            "provenance": "[searxng: search]",
        }
    ]
    with patch(
        "src.web_research.service.search_searxng",
        new=AsyncMock(return_value=searx_hits),
    ) as searx_mock, patch(
        "src.web_research.service.search_serpapi",
        new=AsyncMock(return_value=[]),
    ) as serp_mock:
        payload = await search_web("marine prepositioning", settings=settings)
    assert payload["provider"] == "searxng"
    assert payload["hit_count"] == 1
    searx_mock.assert_awaited_once()
    serp_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_web_falls_back_to_serpapi() -> None:
    settings = _settings(serpapi_api_key="serp")
    serp_hits = [
        {
            "title": "B",
            "url": "https://example.com/b",
            "snippet": "two",
            "provider": "serpapi",
            "rank": 1,
            "provenance": "[serpapi: search]",
        }
    ]
    with patch(
        "src.web_research.service.search_searxng",
        new=AsyncMock(return_value=[]),
    ), patch(
        "src.web_research.service.search_serpapi",
        new=AsyncMock(return_value=serp_hits),
    ):
        payload = await search_web("tagup manifest", settings=settings)
    assert payload["provider"] == "serpapi"
    assert payload["hits"][0]["url"].endswith("/b")


@pytest.mark.asyncio
async def test_fetch_page_standard_chain_stops_on_first_success() -> None:
    settings = _settings(olostep_api_key="olo", max_content_chars=1000)
    direct_fail = {
        "url": "https://tagup.ai/platform",
        "provider": "direct",
        "ok": False,
        "error": "insufficient",
        "content": "",
    }
    olostep_ok = {
        "url": "https://tagup.ai/platform",
        "provider": "olostep",
        "ok": True,
        "content": "Manifest platform overview",
        "content_format": "markdown",
        "provenance": "[olostep: https://tagup.ai/platform]",
    }
    with patch(
        "src.web_research.service.fetch_direct",
        new=AsyncMock(return_value=direct_fail),
    ) as direct_mock, patch(
        "src.web_research.service.fetch_crawl4ai",
        new=AsyncMock(return_value={"ok": False, "error": "skip"}),
    ) as crawl_mock, patch(
        "src.web_research.service.fetch_olostep",
        new=AsyncMock(return_value=olostep_ok),
    ) as olostep_mock, patch(
        "src.web_research.service.fetch_firecrawl",
        new=AsyncMock(),
    ) as firecrawl_mock:
        payload = await fetch_page("https://tagup.ai/platform", settings=settings)
    assert payload["ok"] is True
    assert payload["provider"] == "olostep"
    direct_mock.assert_awaited_once()
    crawl_mock.assert_awaited_once()
    olostep_mock.assert_awaited_once()
    firecrawl_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_page_premium_prefers_firecrawl() -> None:
    settings = _settings(firecrawl_api_key="fc", olostep_api_key="olo")
    firecrawl_ok = {
        "url": "https://tagup.ai/platform",
        "provider": "firecrawl",
        "ok": True,
        "content": "Premium markdown",
        "content_format": "markdown",
        "provenance": "[firecrawl: https://tagup.ai/platform]",
    }
    with patch(
        "src.web_research.service.fetch_firecrawl",
        new=AsyncMock(return_value=firecrawl_ok),
    ) as firecrawl_mock, patch(
        "src.web_research.service.fetch_olostep",
        new=AsyncMock(),
    ) as olostep_mock:
        payload = await fetch_page(
            "https://tagup.ai/platform",
            quality="premium",
            settings=settings,
        )
    assert payload["provider"] == "firecrawl"
    firecrawl_mock.assert_awaited_once()
    olostep_mock.assert_not_awaited()


def test_tool_registry_includes_web_tools() -> None:
    from src.skills.tool_registry import build_tool_specs

    names = {spec.name for spec in build_tool_specs()}
    assert {"web_search", "web_fetch", "web_research", "web_provider_status"} <= names