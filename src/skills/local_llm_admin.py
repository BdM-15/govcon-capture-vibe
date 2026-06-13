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


def admin_model_configured() -> bool:
    return bool(
        str(os.getenv("THESEUS_ADMIN_LLM_MODEL") or "").strip()
        and str(os.getenv("THESEUS_ADMIN_LLM_HOST") or "").strip()
    )


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