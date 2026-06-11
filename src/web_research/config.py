"""Environment-driven configuration for web research providers."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from src.core.env import env_float, env_int

_PLACEHOLDER_FRAGMENTS = (
    "your_",
    "paste_",
    "changeme",
    "example",
    "xxx",
)


def _clean(val: str | None) -> str:
    if not val:
        return ""
    return val.split("#", 1)[0].strip()


def _is_placeholder(val: str) -> bool:
    if not val:
        return True
    low = val.lower()
    return any(fragment in low for fragment in _PLACEHOLDER_FRAGMENTS)


def _configured_key(name: str) -> bool:
    raw = _clean(os.getenv(name))
    return bool(raw) and not _is_placeholder(raw)


def env_bool(name: str, default: bool = False) -> bool:
    raw = _clean(os.getenv(name))
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WebResearchSettings:
    serpapi_api_key: str
    olostep_api_key: str
    firecrawl_api_key: str
    searxng_base_url: str
    enabled: bool
    enable_search: bool
    enable_fetch: bool
    enable_firecrawl: bool
    enable_direct_fetch: bool
    enable_crawl4ai: bool
    fetch_timeout_seconds: float
    max_content_chars: int
    max_search_results: int
    cache_ttl_seconds: int
    cache_dir_name: str

    @property
    def serpapi_configured(self) -> bool:
        return bool(self.serpapi_api_key)

    @property
    def olostep_configured(self) -> bool:
        return bool(self.olostep_api_key)

    @property
    def firecrawl_configured(self) -> bool:
        return bool(self.firecrawl_api_key)

    @property
    def searxng_configured(self) -> bool:
        return bool(self.searxng_base_url)

    def firecrawl_allowed(self, *, quality: str = "standard") -> bool:
        if not self.firecrawl_configured:
            return False
        if quality == "premium":
            return True
        return self.enable_firecrawl


def _env_web_research_settings() -> WebResearchSettings:
    return WebResearchSettings(
        serpapi_api_key=_clean(os.getenv("SERPAPI_API_KEY"))
        if _configured_key("SERPAPI_API_KEY")
        else "",
        olostep_api_key=_clean(os.getenv("OLOSTEP_API_KEY"))
        if _configured_key("OLOSTEP_API_KEY")
        else "",
        firecrawl_api_key=_clean(os.getenv("FIRECRAWL_API_KEY"))
        if _configured_key("FIRECRAWL_API_KEY")
        else "",
        searxng_base_url=_clean(os.getenv("SEARXNG_BASE_URL")).rstrip("/"),
        enabled=True,
        enable_search=True,
        enable_fetch=True,
        enable_firecrawl=env_bool("WEB_RESEARCH_ENABLE_FIRECRAWL", False),
        enable_direct_fetch=True,
        enable_crawl4ai=True,
        fetch_timeout_seconds=env_float("WEB_RESEARCH_FETCH_TIMEOUT", 30.0, 3.0, 300.0),
        max_content_chars=env_int("WEB_RESEARCH_MAX_CONTENT_CHARS", 12_000, 500, 200_000),
        max_search_results=env_int("WEB_RESEARCH_MAX_SEARCH_RESULTS", 8, 1, 20),
        cache_ttl_seconds=env_int("WEB_RESEARCH_CACHE_TTL_SECONDS", 86_400, 0, 2_592_000),
        cache_dir_name=_clean(os.getenv("WEB_RESEARCH_CACHE_DIR")) or "_web_research_cache",
    )


def _coerce_ui_overrides(overrides: dict[str, Any]) -> dict[str, Any]:
    coerced: dict[str, Any] = {}
    bool_keys = (
        "enabled",
        "enable_search",
        "enable_fetch",
        "enable_firecrawl",
        "enable_direct_fetch",
        "enable_crawl4ai",
    )
    for key in bool_keys:
        if key in overrides:
            coerced[key] = bool(overrides[key])
    if "fetch_timeout_seconds" in overrides:
        coerced["fetch_timeout_seconds"] = float(overrides["fetch_timeout_seconds"])
    if "max_content_chars" in overrides:
        coerced["max_content_chars"] = int(overrides["max_content_chars"])
    if "max_search_results" in overrides:
        coerced["max_search_results"] = int(overrides["max_search_results"])
    if "cache_ttl_seconds" in overrides:
        coerced["cache_ttl_seconds"] = int(overrides["cache_ttl_seconds"])
    return coerced


def apply_ui_overrides(
    base: WebResearchSettings,
    overrides: dict[str, Any],
) -> WebResearchSettings:
    return replace(base, **_coerce_ui_overrides(overrides))


def web_research_settings(*, workspace_dir: Path | None = None) -> WebResearchSettings:
    """Return effective settings: env secrets + optional per-workspace UI overrides."""
    base = _env_web_research_settings()
    if workspace_dir is None:
        return base
    from src.web_research.settings_store import WebResearchSettingsStore

    store = WebResearchSettingsStore(lambda: workspace_dir)
    return apply_ui_overrides(base, store.read())