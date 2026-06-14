"""Local Ollama helpers for light administrative tasks (acronym expand, etc.)."""

from __future__ import annotations

import logging
import re
from typing import Any

from src.core import get_settings
from src.server.ollama_llm import (
    is_ollama_available,
    list_available_models,
    ollama_chat,
    ollama_stats_payload,
    resolve_ollama_model,
)
from src.server.runtime_state import get_ollama_status

logger = logging.getLogger(__name__)

_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}(?:-[A-Z]{2,})?\b")

ADMIN_TASKS = frozenset(
    {
        "expand_acronyms",
        "dedupe_claim_gap",
        "split_readiness_proof",
        "query_reformulation",
    }
)

_FIX_HINT = "Start Ollama, confirm Settings → Ollama host/model, then retry."


def admin_model_configured() -> bool:
    """True when Ollama is reachable (same host/model as Settings → Ollama)."""
    return is_ollama_available(get_settings())


def admin_llm_status(*, live_probe: bool = True) -> dict[str, Any]:
    """Unified admin LLM status — always the configured Ollama instance."""
    settings = get_settings()
    payload = ollama_stats_payload(get_ollama_status(), settings)
    payload["roles"] = ["admin_tasks", "handoff_compose"]
    payload["label"] = "Ollama (local admin)"
    if live_probe and not payload.get("ready"):
        host = str(payload.get("host") or settings.ollama_host)
        models = list_available_models(host)
        if models:
            payload["ready"] = True
            payload["state"] = "reachable"
            payload["available_models"] = models
            payload["model"] = resolve_ollama_model(settings)
            payload["error"] = None
    if not payload.get("ready"):
        payload["fix_hint"] = _FIX_HINT
        if not payload.get("error"):
            state = str(payload.get("state") or "unavailable")
            if state in {"unavailable", "unknown"}:
                payload["error"] = "Ollama unreachable"
            elif state == "warmup_failed":
                payload["error"] = payload.get("error") or "Ollama warmup failed"
    return payload


async def build_admin_chat_fn() -> Any:
    """Chat fn for admin tasks — uses Ollama /api/chat via shared settings."""
    settings = get_settings()

    async def _chat(prompt: str) -> str:
        timeout = float(getattr(settings, "ollama_compose_timeout", 120.0) or 120.0)
        return await ollama_chat(
            [{"role": "user", "content": prompt}],
            settings=settings,
            temperature=0.1,
            max_tokens=8192,
            timeout=timeout,
        )

    return _chat


def undefined_acronyms(text: str, *, allowlist: frozenset[str] | None = None) -> list[str]:
    allowed = allowlist or frozenset()
    found: list[str] = []
    seen: set[str] = set()
    for match in _ACRONYM_RE.finditer(str(text or "")):
        token = match.group(0)
        if token in allowed or token in seen:
            continue
        seen.add(token)
        found.append(token)
    return found


def _extract_json_object(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    elif not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        import json

        loaded = json.loads(text)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


async def expand_acronyms_in_text(
    text: str,
    *,
    undefined: list[str] | None = None,
    chat_fn: Any = None,
) -> str:
    targets = undefined or undefined_acronyms(text)
    if not targets or not admin_model_configured():
        return text
    if chat_fn is None:
        chat_fn = await build_admin_chat_fn()

    prompt = (
        "Expand ONLY these acronyms on first use as Full Term (ACR). "
        "Do not change structure, headings, or facts. Return the full revised text.\n"
        f"Acronyms: {', '.join(targets[:12])}\n\n"
        f"Text:\n{text[:12_000]}"
    )
    try:
        revised = await chat_fn(prompt)
        return str(revised or text).strip() or text
    except Exception as exc:  # noqa: BLE001
        logger.warning("admin_llm expand_acronyms failed: %s", exc)
        return text


async def expand_acronyms_in_eval_handoff_json(
    content: str,
    *,
    chat_fn: Any = None,
) -> str:
    import json

    from src.skills.readiness_content_gates import (
        acronym_issues_for_eval_handoff,
        eval_handoff_text_for_acronym_gate,
        undefined_acronyms as gate_undefined_acronyms,
    )

    if not admin_model_configured():
        return content
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return content
    if not isinstance(payload, dict) or not acronym_issues_for_eval_handoff(payload):
        return content
    targets = gate_undefined_acronyms(eval_handoff_text_for_acronym_gate(payload))
    if not targets:
        return content
    if chat_fn is None:
        chat_fn = await build_admin_chat_fn()

    prompt = (
        "Expand ONLY undefined acronyms on first use as Full Term (ACR) in readiness_link, "
        "proof_expected, and claim_gaps[] strings inside this eval_handoff JSON. "
        "Do not change evaluation_factor labels, source_chunk_ids, array order, or facts. "
        "Return ONE valid JSON object only.\n"
        f"Acronyms: {', '.join(targets[:16])}\n\n"
        f"JSON:\n{content[:14_000]}"
    )
    try:
        revised_raw = await chat_fn(prompt)
        parsed = _extract_json_object(str(revised_raw or ""))
        if not parsed:
            return content
        return json.dumps(parsed, ensure_ascii=False, indent=2) + "\n"
    except Exception as exc:  # noqa: BLE001
        logger.warning("admin_llm eval_handoff expand_acronyms failed: %s", exc)
        return content


__all__ = [
    "ADMIN_TASKS",
    "admin_llm_status",
    "admin_model_configured",
    "build_admin_chat_fn",
    "expand_acronyms_in_eval_handoff_json",
    "expand_acronyms_in_text",
    "undefined_acronyms",
]