"""Ollama warm-start helper — polls /api/tags and returns reachability."""
from __future__ import annotations

import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


def manage_ollama_startup(ollama_host: str = "http://localhost:11434") -> bool:
    """Probe Ollama health endpoint. Non-fatal — Theseus boots normally either way.

    Args:
        ollama_host: Base URL of the Ollama server (no trailing slash).

    Returns:
        True if Ollama responds with HTTP 200, False otherwise.
    """
    url = f"{ollama_host.rstrip('/')}/api/tags"
    logger.info("🔍 Checking Ollama at %s …", url)
    print("🔍 Checking Ollama...")
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                logger.info("✅ Ollama reachable — vault polish enabled")
                print("✅ Ollama reachable — vault polish enabled\n")
                return True
    except (urllib.error.URLError, OSError, Exception) as exc:
        logger.warning("⚠️  Ollama not reachable (%s) — vault polish disabled", exc)
    print("⚠️  Ollama not reachable — vault polish disabled (start Ollama to enable)\n")
    return False
