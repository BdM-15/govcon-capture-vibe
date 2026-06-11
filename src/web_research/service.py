"""Orchestration for search, fetch, and combined research."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.web_research.cache import cache_get, cache_set
from src.web_research.config import WebResearchSettings, web_research_settings
from src.web_research.providers import (
    fetch_crawl4ai,
    fetch_direct,
    fetch_firecrawl,
    fetch_olostep,
    search_searxng,
    search_serpapi,
)

logger = logging.getLogger(__name__)


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + "\n…[truncated]", True


def provider_status(settings: WebResearchSettings | None = None) -> dict[str, Any]:
    """Return configured providers without exposing secrets."""
    cfg = settings or web_research_settings()
    return {
        "search": [
            {
                "id": "searxng",
                "tier": "free",
                "configured": cfg.searxng_configured,
            },
            {
                "id": "serpapi",
                "tier": "api",
                "configured": cfg.serpapi_configured,
            },
        ],
        "fetch": [
            {"id": "direct", "tier": "free", "configured": True},
            {
                "id": "crawl4ai",
                "tier": "free",
                "configured": _crawl4ai_available(),
            },
            {
                "id": "olostep",
                "tier": "api",
                "configured": cfg.olostep_configured,
            },
            {
                "id": "firecrawl",
                "tier": "premium",
                "configured": cfg.firecrawl_configured,
                "enabled_in_chain": cfg.enable_firecrawl,
                "premium_on_demand": cfg.firecrawl_configured,
            },
        ],
        "policy": {
            "enabled": cfg.enabled,
            "enable_search": cfg.enable_search,
            "enable_fetch": cfg.enable_fetch,
            "search_order": ["searxng", "serpapi"],
            "fetch_standard_order": _standard_fetch_order(cfg),
            "fetch_premium_order": _premium_fetch_order(cfg),
            "firecrawl_global_enabled": cfg.enable_firecrawl,
        },
    }


def _crawl4ai_available() -> bool:
    try:
        import crawl4ai  # noqa: F401

        return True
    except ImportError:
        return False


def _standard_fetch_order(cfg: WebResearchSettings) -> list[str]:
    order: list[str] = []
    if cfg.enable_direct_fetch:
        order.append("direct")
    if cfg.enable_crawl4ai:
        order.append("crawl4ai")
    if cfg.olostep_configured:
        order.append("olostep")
    if cfg.firecrawl_allowed(quality="standard"):
        order.append("firecrawl")
    return order


def _premium_fetch_order(cfg: WebResearchSettings) -> list[str]:
    order: list[str] = []
    if cfg.firecrawl_allowed(quality="premium"):
        order.append("firecrawl")
    if cfg.olostep_configured:
        order.append("olostep")
    if cfg.enable_crawl4ai:
        order.append("crawl4ai")
    if cfg.enable_direct_fetch:
        order.append("direct")
    return order


def _cache_dir(workspace_dir: Path | None, settings: WebResearchSettings) -> Path | None:
    if settings.cache_ttl_seconds <= 0:
        return None
    base = workspace_dir if workspace_dir is not None else Path.cwd()
    return (base / settings.cache_dir_name).resolve()


def _require_enabled(cfg: WebResearchSettings) -> None:
    if not cfg.enabled:
        raise ValueError(
            "external web research is disabled — enable it in Settings → Web Research"
        )


async def search_web(
    query: str,
    *,
    limit: int | None = None,
    settings: WebResearchSettings | None = None,
    workspace_dir: Path | None = None,
) -> dict[str, Any]:
    """Search the public web using free-first provider order."""
    cfg = settings or web_research_settings(workspace_dir=workspace_dir)
    _require_enabled(cfg)
    if not cfg.enable_search:
        raise ValueError("web search is disabled in Settings → Web Research")
    q = str(query or "").strip()
    if not q:
        raise ValueError("query must be non-empty")
    max_hits = min(limit or cfg.max_search_results, cfg.max_search_results)

    cache_key = f"search:{q}:{max_hits}"
    cache_path = _cache_dir(workspace_dir, cfg)
    if cache_path is not None:
        cached = cache_get(cache_path, "search", cache_key, ttl_seconds=cfg.cache_ttl_seconds)
        if cached is not None:
            cached["cache_hit"] = True
            return cached

    attempts: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    provider = ""
    for candidate, runner in (
        ("searxng", lambda: search_searxng(q, cfg, limit=max_hits)),
        ("serpapi", lambda: search_serpapi(q, cfg, limit=max_hits)),
    ):
        rows = await runner()
        attempts.append({"provider": candidate, "hits": len(rows)})
        if rows:
            hits = rows
            provider = candidate
            break

    payload = {
        "query": q,
        "provider": provider,
        "hits": hits,
        "hit_count": len(hits),
        "attempts": attempts,
        "cache_hit": False,
        "provenance_class": "external",
    }
    if cache_path is not None:
        cache_set(cache_path, "search", cache_key, payload)
    return payload


async def fetch_page(
    url: str,
    *,
    quality: str = "standard",
    settings: WebResearchSettings | None = None,
    workspace_dir: Path | None = None,
) -> dict[str, Any]:
    """Fetch and extract page content with provider fallback."""
    cfg = settings or web_research_settings(workspace_dir=workspace_dir)
    _require_enabled(cfg)
    if not cfg.enable_fetch:
        raise ValueError("web fetch is disabled in Settings → Web Research")
    normalized_quality = "premium" if str(quality or "").strip().lower() == "premium" else "standard"
    target = str(url or "").strip()
    if not target:
        raise ValueError("url must be non-empty")

    cache_key = f"fetch:{normalized_quality}:{target}"
    cache_path = _cache_dir(workspace_dir, cfg)
    if cache_path is not None:
        cached = cache_get(cache_path, "fetch", cache_key, ttl_seconds=cfg.cache_ttl_seconds)
        if cached is not None:
            cached["cache_hit"] = True
            return cached

    order = (
        _premium_fetch_order(cfg)
        if normalized_quality == "premium"
        else _standard_fetch_order(cfg)
    )
    runners = {
        "direct": lambda: fetch_direct(target, cfg),
        "crawl4ai": lambda: fetch_crawl4ai(target, cfg),
        "olostep": lambda: fetch_olostep(target, cfg),
        "firecrawl": lambda: fetch_firecrawl(target, cfg),
    }

    attempts: list[dict[str, Any]] = []
    winner: dict[str, Any] | None = None
    for provider_id in order:
        runner = runners.get(provider_id)
        if runner is None:
            continue
        result = await runner()
        attempts.append(
            {
                "provider": provider_id,
                "ok": bool(result.get("ok")),
                "error": result.get("error") or "",
            }
        )
        if result.get("ok"):
            winner = result
            break

    if winner is None:
        payload = {
            "url": target,
            "quality": normalized_quality,
            "ok": False,
            "provider": "",
            "content": "",
            "title": "",
            "attempts": attempts,
            "error": "all fetch providers failed",
            "cache_hit": False,
            "provenance_class": "external",
        }
        return payload

    content, truncated = _truncate(str(winner.get("content") or ""), cfg.max_content_chars)
    payload = {
        "url": target,
        "quality": normalized_quality,
        "ok": True,
        "provider": winner.get("provider"),
        "title": winner.get("title") or "",
        "content": content,
        "content_format": winner.get("content_format") or "text",
        "status_code": winner.get("status_code"),
        "provenance": winner.get("provenance"),
        "truncated": truncated,
        "attempts": attempts,
        "cache_hit": False,
        "provenance_class": "external",
    }
    if cache_path is not None:
        cache_set(cache_path, "fetch", cache_key, payload)
    return payload


async def research(
    *,
    queries: list[str] | None = None,
    urls: list[str] | None = None,
    fetch_quality: str = "standard",
    max_fetches: int = 3,
    settings: WebResearchSettings | None = None,
    workspace_dir: Path | None = None,
) -> dict[str, Any]:
    """Run search queries and fetch explicit URLs in one call."""
    cfg = settings or web_research_settings(workspace_dir=workspace_dir)
    _require_enabled(cfg)
    query_list = [str(q).strip() for q in (queries or []) if str(q).strip()]
    url_list = [str(u).strip() for u in (urls or []) if str(u).strip()]
    if not query_list and not url_list:
        raise ValueError("at least one query or url is required")

    searches: list[dict[str, Any]] = []
    for query in query_list[: cfg.max_search_results]:
        searches.append(
            await search_web(query, settings=cfg, workspace_dir=workspace_dir)
        )

    discovered_urls: list[str] = []
    for block in searches:
        for hit in block.get("hits") or []:
            link = str((hit or {}).get("url") or "").strip()
            if link and link not in discovered_urls:
                discovered_urls.append(link)

    fetch_targets: list[str] = []
    for url in url_list:
        if url not in fetch_targets:
            fetch_targets.append(url)
    for url in discovered_urls:
        if len(fetch_targets) >= max(0, max_fetches):
            break
        if url not in fetch_targets:
            fetch_targets.append(url)

    fetches: list[dict[str, Any]] = []
    if max_fetches > 0:
        for url in fetch_targets[:max_fetches]:
            fetches.append(
                await fetch_page(
                    url,
                    quality=fetch_quality,
                    settings=cfg,
                    workspace_dir=workspace_dir,
                )
            )

    return {
        "searches": searches,
        "fetches": fetches,
        "query_count": len(searches),
        "fetch_count": len(fetches),
        "provider_status": provider_status(cfg),
        "provenance_class": "external",
    }