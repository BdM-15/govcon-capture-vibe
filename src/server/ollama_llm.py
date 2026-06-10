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


def _base_status(settings: Any) -> dict[str, Any]:
    host = getattr(settings, "ollama_host", "http://localhost:11434")
    configured = getattr(settings, "ollama_model", "qwen3.5:9b")
    return {
        "ok": False,
        "state": "unavailable",
        "model": configured,
        "configured_model": configured,
        "host": host,
        "available": [],
        "keyword_binding": getattr(settings, "keyword_llm_binding", "openai"),
        "keyword_model": getattr(settings, "keyword_llm_name", configured),
        "keyword_uses_ollama": bool(getattr(settings, "keyword_uses_ollama", False)),
        "warmed_at": None,
        "error": None,
    }


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


def _generate_sync(
    *,
    host: str,
    model: str,
    prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 8,
    timeout: float = 30.0,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        result = json.loads(response.read())
    text = str(result.get("response") or "").strip()
    if not text:
        raise RuntimeError("Ollama generate returned empty response")
    return text


def warmup_ollama_sync(settings: Any, *, timeout: float = 45.0) -> dict[str, Any]:
    """Synchronous startup warmup for app.py; loads the configured model into memory."""
    info = _base_status(settings)
    host = str(info["host"])
    try:
        info["available"] = list_available_models(host)
        if not info["available"]:
            info["error"] = "no models reported"
            info["state"] = "unavailable"
            return info
        info["state"] = "reachable"
        info["model"] = resolve_ollama_model(settings)
        _generate_sync(
            host=host,
            model=info["model"],
            prompt="Say ready.",
            temperature=0.0,
            max_tokens=8,
            timeout=timeout,
        )
        info["ok"] = True
        info["state"] = "ready"
        from src.utils.time_utils import now_local_iso

        info["warmed_at"] = now_local_iso(timespec="seconds")
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)[:160]
        if info["available"]:
            info["state"] = "warmup_failed"
    return info


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
    """Async startup warmup used when sync warmup did not run or failed."""
    info = _base_status(settings)
    host = str(info["host"])
    try:
        info["available"] = list_available_models(host)
        if not info["available"]:
            info["error"] = "no models reported"
            info["state"] = "unavailable"
            return info
        info["state"] = "reachable"
        info["model"] = resolve_ollama_model(settings)
        _ = await ollama_chat(
            [{"role": "user", "content": "Say ready."}],
            settings=settings,
            model=info["model"],
            max_tokens=8,
            temperature=0.0,
            timeout=20.0,
        )
        info["ok"] = True
        info["state"] = "ready"
        from src.utils.time_utils import now_local_iso

        info["warmed_at"] = now_local_iso(timespec="seconds")
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)[:160]
        if info["available"]:
            info["state"] = "warmup_failed"
    return info


def format_ollama_banner_line(status: dict[str, Any] | None, settings: Any, colors: Any) -> str:
    """Render the Ollama row for the startup banner."""
    model = getattr(settings, "ollama_model", "qwen3.5:9b")
    host = getattr(settings, "ollama_host", "http://localhost:11434")
    if not status:
        return (
            f"{colors.YELLOW}{model}{colors.RESET}"
            f"  {colors.DIM}·  {host}  ·  not warmed{colors.RESET}"
        )
    resolved = status.get("model") or model
    state = status.get("state") or ("ready" if status.get("ok") else "unavailable")
    if state == "ready":
        state_color = colors.GREEN
        state_label = "READY"
    elif state == "warmup_failed":
        state_color = colors.YELLOW
        state_label = "WARMUP FAILED"
    elif state == "reachable":
        state_color = colors.YELLOW
        state_label = "REACHABLE"
    else:
        state_color = colors.YELLOW
        state_label = "UNAVAILABLE"
    return (
        f"{colors.CYAN}{resolved}{colors.RESET}"
        f"  {colors.DIM}·  {host}{colors.RESET}"
        f"  ·  {colors.BOLD}{state_color}{state_label}{colors.RESET}"
    )


def log_ollama_startup(status: dict[str, Any] | None, *, logger_obj: Any | None = None) -> None:
    """Write Ollama warmup results to server logs."""
    log = logger_obj or logger
    if not status:
        log.info("ℹ️ Ollama warmup status unavailable")
        return
    host = status.get("host")
    model = status.get("model")
    if status.get("ok"):
        log.info(
            "✅ Ollama warmup complete: model=%s host=%s models=%d keyword_binding=%s",
            model,
            host,
            len(status.get("available") or []),
            status.get("keyword_binding"),
        )
        return
    if status.get("available"):
        log.warning(
            "⚠️ Ollama reachable but warmup failed at %s (model=%s): %s",
            host,
            model,
            status.get("error", "unknown"),
        )
        return
    log.warning(
        "⚠️ Ollama unavailable at %s — handoff compose falls back; keyword role may fail if binding=ollama (%s)",
        host,
        status.get("keyword_binding"),
    )


def ollama_stats_payload(status: dict[str, Any] | None, settings: Any) -> dict[str, Any]:
    """Shape Ollama status for /api/ui/stats."""
    base = {
        "host": getattr(settings, "ollama_host", "http://localhost:11434"),
        "model": getattr(settings, "ollama_model", "qwen3.5:9b"),
        "state": "unknown",
        "ready": False,
        "available_models": [],
        "warmed_at": None,
        "error": None,
        "keyword_binding": getattr(settings, "keyword_llm_binding", "openai"),
        "keyword_model": getattr(settings, "keyword_llm_name", None),
    }
    if not status:
        return base
    base.update(
        {
            "host": status.get("host") or base["host"],
            "model": status.get("model") or base["model"],
            "state": status.get("state") or ("ready" if status.get("ok") else "unavailable"),
            "ready": bool(status.get("ok")),
            "available_models": list(status.get("available") or []),
            "warmed_at": status.get("warmed_at"),
            "error": status.get("error"),
            "keyword_binding": status.get("keyword_binding") or base["keyword_binding"],
            "keyword_model": status.get("keyword_model") or base["keyword_model"],
        }
    )
    return base