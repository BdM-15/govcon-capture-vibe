"""Per-workspace UI overrides for external web research."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from src.core.env import env_float, env_int
from src.web_research.config import env_bool

logger = logging.getLogger(__name__)

UI_SETTING_KEYS = (
    "enabled",
    "enable_search",
    "enable_fetch",
    "enable_firecrawl",
    "enable_direct_fetch",
    "enable_crawl4ai",
    "fetch_timeout_seconds",
    "max_content_chars",
    "max_search_results",
    "cache_ttl_seconds",
)


class WebResearchSettingsStore:
    """Persist non-secret web research toggles per workspace."""

    def __init__(self, workspace_dir: Callable[[], Path]) -> None:
        self._workspace_dir = workspace_dir

    def path(self) -> Path:
        return self._workspace_dir() / "ui_web_research_settings.json"

    def defaults(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "enable_search": True,
            "enable_fetch": True,
            "enable_firecrawl": env_bool("WEB_RESEARCH_ENABLE_FIRECRAWL", False),
            "enable_direct_fetch": True,
            "enable_crawl4ai": True,
            "fetch_timeout_seconds": env_float(
                "WEB_RESEARCH_FETCH_TIMEOUT", 30.0, 3.0, 300.0
            ),
            "max_content_chars": env_int(
                "WEB_RESEARCH_MAX_CONTENT_CHARS", 12_000, 500, 200_000
            ),
            "max_search_results": env_int(
                "WEB_RESEARCH_MAX_SEARCH_RESULTS", 8, 1, 20
            ),
            "cache_ttl_seconds": env_int(
                "WEB_RESEARCH_CACHE_TTL_SECONDS", 86_400, 0, 2_592_000
            ),
        }

    def read(self) -> dict[str, Any]:
        merged = self.defaults()
        path = self.path()
        if not path.exists():
            return merged
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key in UI_SETTING_KEYS:
                    if key in loaded:
                        merged[key] = loaded[key]
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed reading %s, using defaults: %s", path, exc)
        return merged

    def write(self, data: dict[str, Any]) -> None:
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        current = self.read()
        for key in UI_SETTING_KEYS:
            if key in data:
                current[key] = data[key]
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def reset(self) -> dict[str, Any]:
        path = self.path()
        if path.exists():
            path.unlink()
        return self.defaults()