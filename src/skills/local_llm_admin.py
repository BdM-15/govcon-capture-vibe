"""Cheap local-model helpers for light administrative tasks only."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}(?:-[A-Z]{2,})?\b")

# Tasks suitable for a local / small model — never research, merge, or full brief synthesis.
ADMIN_TASKS = frozenset(
    {
        "expand_acronyms",
        "dedupe_claim_gap",
        "split_readiness_proof",
        "query_reformulation",
    }
)


def _admin_llm_host() -> str:
    explicit = str(os.getenv("THESEUS_ADMIN_LLM_HOST") or "").strip()
    if explicit:
        return explicit
    ollama = str(os.getenv("OLLAMA_HOST") or "http://localhost:11434").strip().rstrip("/")
    return f"{ollama}/v1"


def _admin_llm_model() -> str:
    return (
        str(os.getenv("THESEUS_ADMIN_LLM_MODEL") or "").strip()
        or str(os.getenv("OLLAMA_MODEL") or "qwen3.5:9b").strip()
    )


def admin_model_configured() -> bool:
    return bool(_admin_llm_host() and _admin_llm_model())


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


async def build_admin_chat_fn() -> Any:
    """OpenAI-compatible chat fn for THESEUS_ADMIN_LLM_* (local Ollama, etc.)."""
    import os

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=os.getenv("THESEUS_ADMIN_LLM_API_KEY", "local"),
        base_url=_admin_llm_host(),
    )
    model = _admin_llm_model()

    async def _chat(prompt: str) -> str:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=8192,
        )
        return str(response.choices[0].message.content or "")

    return _chat


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
    """Expand undefined acronyms in a text block using the admin model when configured."""
    targets = undefined or undefined_acronyms(text)
    if not targets or not admin_model_configured():
        return text
    if chat_fn is None:
        logger.info("admin_llm: expand_acronyms skipped (no chat_fn)")
        return text

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
    """Expand acronyms in eval handoff prose fields via admin LLM — cheap, not main model."""
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