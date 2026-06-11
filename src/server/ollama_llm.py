"""Local Ollama client for Theseus insight handoff packaging."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

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


def _warmup_text_from_payload(payload: dict[str, Any]) -> str:
    try:
        return _text_from_chat_payload(payload)
    except RuntimeError as exc:
        raise RuntimeError("Ollama warmup returned empty content") from exc


def _chat_sync(
    *,
    host: str,
    model: str,
    prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 24,
    timeout: float = 60.0,
) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        result = json.loads(response.read())
    return _warmup_text_from_payload(result)


def _warmup_model_sync(
    *,
    host: str,
    model: str,
    timeout: float,
) -> None:
    _chat_sync(
        host=host,
        model=model,
        prompt="Reply with exactly: ready",
        temperature=0.0,
        max_tokens=24,
        timeout=timeout,
    )


def warmup_ollama_sync(settings: Any, *, timeout: float = 90.0) -> dict[str, Any]:
    """Synchronous startup warmup for app.py; loads the handoff compose model."""
    info = _base_status(settings)
    host = str(info["host"])
    try:
        info["available"] = list_available_models(host)
        if not info["available"]:
            info["error"] = "no models reported"
            info["state"] = "unavailable"
            return info
        info["state"] = "reachable"
        curation_model = resolve_ollama_model(settings)
        info["model"] = curation_model
        _warmup_model_sync(host=host, model=curation_model, timeout=timeout)
        info["ok"] = True
        info["state"] = "ready"
        from src.utils.time_utils import now_local_iso

        info["warmed_at"] = now_local_iso(timespec="seconds")
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)[:160]
        if info["available"]:
            info["state"] = "warmup_failed"
    return info


def _text_from_chat_payload(payload: dict[str, Any]) -> str:
    """Extract assistant text from Ollama /api/chat payloads."""
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    for key in ("content", "response"):
        text = str(payload.get(key) or message.get(key) or "").strip()
        if text:
            return text
    for key in ("thinking",):
        text = str(payload.get(key) or message.get(key) or "").strip()
        if text:
            return text
    raise RuntimeError("Ollama returned empty content")


async def ollama_chat(
    messages: list[dict[str, str]],
    *,
    settings: Any,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int = 1200,
    timeout: float = 45.0,
) -> str:
    """Async chat completion against Ollama /api/chat."""
    import httpx

    chosen = resolve_ollama_model(settings, model=model)
    temp = (
        float(temperature)
        if temperature is not None
        else float(getattr(settings, "ollama_temperature", 0.3))
    )
    host = getattr(settings, "ollama_host", "http://localhost:11434").rstrip("/")
    payload = {
        "model": chosen,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temp, "num_predict": max_tokens},
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{host}/api/chat",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Ollama returned invalid JSON payload")
    return _text_from_chat_payload(data)


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
        _warmup_model_sync(
            host=host,
            model=info["model"],
            timeout=60.0,
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
            "✅ Ollama warmup complete: model=%s host=%s models=%d",
            model,
            host,
            len(status.get("available") or []),
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
        "⚠️ Ollama unavailable at %s — handoff compose falls back to mechanical seed",
        host,
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
        }
    )
    return base