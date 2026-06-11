"""Provider adapters for search and page fetch."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode, urlparse

from src.web_research.config import WebResearchSettings
from src.web_research.html import html_to_text

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; ProjectTheseus/1.0; +https://github.com/BdM-15/govcon-capture-vibe)"
)


async def _http_client():
    import httpx

    return httpx


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {url!r}")
    if not parsed.netloc:
        raise ValueError(f"invalid URL: {url!r}")
    return url.strip()


def _search_hit(
    *,
    title: str,
    url: str,
    snippet: str,
    provider: str,
    rank: int,
) -> dict[str, Any]:
    return {
        "title": title.strip(),
        "url": url.strip(),
        "snippet": snippet.strip(),
        "provider": provider,
        "rank": rank,
        "provenance": f"[{provider}: search]",
    }


def _page_result(
    *,
    url: str,
    provider: str,
    title: str = "",
    content: str = "",
    content_format: str = "text",
    status_code: int | None = None,
    error: str = "",
) -> dict[str, Any]:
    return {
        "url": url,
        "provider": provider,
        "title": title.strip(),
        "content": content,
        "content_format": content_format,
        "status_code": status_code,
        "error": error,
        "provenance": f"[{provider}: {url}]",
        "ok": bool(content.strip()) and not error,
    }


async def fetch_direct(url: str, settings: WebResearchSettings) -> dict[str, Any]:
    url = _normalize_url(url)
    httpx = await _http_client()
    try:
        async with httpx.AsyncClient(
            timeout=settings.fetch_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            response = await client.get(url)
    except Exception as exc:  # noqa: BLE001
        return _page_result(url=url, provider="direct", error=str(exc))

    content_type = (response.headers.get("content-type") or "").lower()
    body = response.text if "text" in content_type or "html" in content_type else ""
    if body and "html" in content_type:
        text = html_to_text(body)
        content_format = "text"
    else:
        text = body.strip()
        content_format = "text"

    if response.status_code >= 400:
        return _page_result(
            url=url,
            provider="direct",
            status_code=response.status_code,
            error=f"HTTP {response.status_code}",
        )
    if len(text) < 120:
        return _page_result(
            url=url,
            provider="direct",
            status_code=response.status_code,
            error="direct fetch returned insufficient text (likely JS-rendered)",
        )
    return _page_result(
        url=url,
        provider="direct",
        content=text,
        content_format=content_format,
        status_code=response.status_code,
    )


async def fetch_olostep(url: str, settings: WebResearchSettings) -> dict[str, Any]:
    if not settings.olostep_configured:
        return _page_result(url=url, provider="olostep", error="OLOSTEP_API_KEY not configured")
    url = _normalize_url(url)
    httpx = await _http_client()
    payload = {"url_to_scrape": url, "formats": ["markdown", "text"]}
    headers = {
        "Authorization": f"Bearer {settings.olostep_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.fetch_timeout_seconds) as client:
            response = await client.post(
                "https://api.olostep.com/v1/scrapes",
                json=payload,
                headers=headers,
            )
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        return _page_result(url=url, provider="olostep", error=str(exc))

    if response.status_code >= 400:
        message = ""
        if isinstance(data, dict):
            err = data.get("error") or {}
            if isinstance(err, dict):
                message = str(err.get("message") or err.get("code") or "")
        return _page_result(
            url=url,
            provider="olostep",
            status_code=response.status_code,
            error=message or f"HTTP {response.status_code}",
        )

    result = (data or {}).get("result") if isinstance(data, dict) else {}
    if not isinstance(result, dict):
        return _page_result(url=url, provider="olostep", error="unexpected Olostep response shape")

    content = str(result.get("markdown_content") or result.get("text_content") or "").strip()
    meta = result.get("page_metadata") if isinstance(result.get("page_metadata"), dict) else {}
    title = str(meta.get("title") or "")
    status_code = meta.get("status_code")
    if not content:
        return _page_result(url=url, provider="olostep", title=title, error="empty Olostep content")
    return _page_result(
        url=url,
        provider="olostep",
        title=title,
        content=content,
        content_format="markdown" if result.get("markdown_content") else "text",
        status_code=int(status_code) if isinstance(status_code, int) else None,
    )


async def fetch_firecrawl(url: str, settings: WebResearchSettings) -> dict[str, Any]:
    if not settings.firecrawl_configured:
        return _page_result(url=url, provider="firecrawl", error="FIRECRAWL_API_KEY not configured")
    url = _normalize_url(url)
    httpx = await _http_client()
    payload = {"url": url, "formats": ["markdown"], "onlyMainContent": True}
    headers = {
        "Authorization": f"Bearer {settings.firecrawl_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=max(settings.fetch_timeout_seconds, 60.0)) as client:
            response = await client.post(
                "https://api.firecrawl.dev/v2/scrape",
                json=payload,
                headers=headers,
            )
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        return _page_result(url=url, provider="firecrawl", error=str(exc))

    if response.status_code >= 400:
        message = ""
        if isinstance(data, dict):
            message = str(data.get("error") or "")
        return _page_result(
            url=url,
            provider="firecrawl",
            status_code=response.status_code,
            error=message or f"HTTP {response.status_code}",
        )

    block = data.get("data") if isinstance(data, dict) else {}
    if not isinstance(block, dict):
        return _page_result(url=url, provider="firecrawl", error="unexpected Firecrawl response shape")
    content = str(block.get("markdown") or block.get("summary") or "").strip()
    meta = block.get("metadata") if isinstance(block.get("metadata"), dict) else {}
    title = str(meta.get("title") or "")
    if not content:
        return _page_result(url=url, provider="firecrawl", title=title, error="empty Firecrawl content")
    return _page_result(
        url=url,
        provider="firecrawl",
        title=title,
        content=content,
        content_format="markdown",
    )


async def fetch_crawl4ai(url: str, settings: WebResearchSettings) -> dict[str, Any]:
    url = _normalize_url(url)
    try:
        from crawl4ai import AsyncWebCrawler
    except ImportError:
        return _page_result(
            url=url,
            provider="crawl4ai",
            error="crawl4ai not installed (optional free JS-render fallback)",
        )

    try:
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url)
    except Exception as exc:  # noqa: BLE001
        return _page_result(url=url, provider="crawl4ai", error=str(exc))

    markdown = str(getattr(result, "markdown", "") or "").strip()
    if not markdown:
        cleaned = str(getattr(result, "cleaned_html", "") or "")
        markdown = html_to_text(cleaned)
    if not markdown:
        return _page_result(url=url, provider="crawl4ai", error="empty crawl4ai content")
    return _page_result(
        url=url,
        provider="crawl4ai",
        content=markdown,
        content_format="markdown",
    )


async def search_searxng(query: str, settings: WebResearchSettings, *, limit: int) -> list[dict[str, Any]]:
    if not settings.searxng_configured:
        return []
    httpx = await _http_client()
    params = urlencode({"q": query, "format": "json"})
    endpoint = f"{settings.searxng_base_url}/search?{params}"
    try:
        async with httpx.AsyncClient(timeout=settings.fetch_timeout_seconds) as client:
            response = await client.get(endpoint, headers={"User-Agent": _USER_AGENT})
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("searxng search failed: %s", exc)
        return []

    results = data.get("results") if isinstance(data, dict) else []
    hits: list[dict[str, Any]] = []
    for idx, row in enumerate(results[:limit], start=1):
        if not isinstance(row, dict):
            continue
        hits.append(
            _search_hit(
                title=str(row.get("title") or ""),
                url=str(row.get("url") or ""),
                snippet=str(row.get("content") or row.get("snippet") or ""),
                provider="searxng",
                rank=idx,
            )
        )
    return hits


async def search_serpapi(query: str, settings: WebResearchSettings, *, limit: int) -> list[dict[str, Any]]:
    if not settings.serpapi_configured:
        return []
    httpx = await _http_client()
    params = urlencode(
        {
            "engine": "google",
            "q": query,
            "api_key": settings.serpapi_api_key,
            "num": str(limit),
        }
    )
    endpoint = f"https://serpapi.com/search.json?{params}"
    try:
        async with httpx.AsyncClient(timeout=settings.fetch_timeout_seconds) as client:
            response = await client.get(endpoint)
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("serpapi search failed: %s", exc)
        return []

    rows = data.get("organic_results") if isinstance(data, dict) else []
    hits: list[dict[str, Any]] = []
    for idx, row in enumerate(rows[:limit], start=1):
        if not isinstance(row, dict):
            continue
        hits.append(
            _search_hit(
                title=str(row.get("title") or ""),
                url=str(row.get("link") or ""),
                snippet=str(row.get("snippet") or ""),
                provider="serpapi",
                rank=idx,
            )
        )
    return hits