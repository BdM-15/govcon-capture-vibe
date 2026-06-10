"""Local Ollama client for Theseus UI curation and optional keyword routing."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

OLLAMA_API_KEY = "ollama"
_PREFERRED_MODEL_KEYWORDS = ("qwen3.5", "qwen3", "qwen2.5", "llama3.1", "mistral-nemo", "instruct")


def list_available_models(host: str, *, timeout: float = 2.0) -> list[str]:
    """Return Ollama model tags (empty when unreachable)."""
    base = host.rstrip("/")
    try:
        req = urllib.request.Request(f"{base}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read())
        models = data.get("models") or []
        return [
            str(item.get("name") or item.get("model") or "").strip()
            for item in models
            if isinstance(item, dict)
        ]
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.debug("Ollama model list unavailable at %s: %s", base, exc)
        return []


def pick_best_model(preferred: str, available: list[str]) -> str:
    """Prefer configured model; otherwise pick a sensible instruct tag."""
    if not available or preferred in available:
        return preferred
    lowered = [name.lower() for name in available]
    for keyword in _PREFERRED_MODEL_KEYWORDS:
        for index, name in enumerate(lowered):
            if keyword in name and "embed" not in name:
                return available[index]
    return available[0]


def resolve_ollama_model(settings: Any, *, model: str | None = None) -> str:
    configured = (model or getattr(settings, "ollama_model", None) or "qwen3.5:9b").strip()
    host = getattr(settings, "ollama_host", "http://localhost:11434")
    return pick_best_model(configured, list_available_models(host))


def is_ollama_available(settings: Any, *, timeout: float = 2.0) -> bool:
    host = getattr(settings, "ollama_host", "http://localhost:11434")
    return bool(list_available_models(host, timeout=timeout))


async def ollama_chat(
    messages: list[dict[str, str]],
    *,
    settings: Any,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int = 1200,
    timeout: float = 45.0,
) -> str:
    """Async chat completion against Ollama's OpenAI-compatible endpoint."""
    import httpx

    chosen = resolve_ollama_model(settings, model=model)
    temp = (
        float(temperature)
        if temperature is not None
        else float(getattr(settings, "ollama_temperature", 0.3))
    )
    base = getattr(settings, "ollama_openai_base_url", None) or (
        f"{getattr(settings, 'ollama_host', 'http://localhost:11434').rstrip('/')}/v1"
    )
    payload = {
        "model": chosen,
        "messages": messages,
        "temperature": temp,
        "max_tokens": max_tokens,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base.rstrip('/')}/chat/completions",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OLLAMA_API_KEY}",
            },
        )
        response.raise_for_status()
        data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Ollama returned no choices")
    message = choices[0].get("message") or {}
    text = str(message.get("content") or "").strip()
    if not text:
        raise RuntimeError("Ollama returned empty content")
    return text


async def warmup_ollama(settings: Any) -> dict[str, Any]:
    """Best-effort startup warmup; never raises."""
    info: dict[str, Any] = {
        "ok": False,
        "model": getattr(settings, "ollama_model", "qwen3.5:9b"),
        "host": getattr(settings, "ollama_host", "http://localhost:11434"),
        "available": [],
    }
    try:
        info["available"] = list_available_models(info["host"])
        if not info["available"]:
            info["error"] = "no models reported"
            return info
        info["model"] = resolve_ollama_model(settings)
        _ = await ollama_chat(
            [{"role": "user", "content": "Say ready."}],
            settings=settings,
            max_tokens=8,
            temperature=0.0,
            timeout=20.0,
        )
        info["ok"] = True
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)[:160]
    return info