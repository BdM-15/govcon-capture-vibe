"""Local Ollama packaging for Capture Chat insight handoff seeds."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.server.ollama_llm import is_ollama_available, ollama_chat, resolve_ollama_model

_DEFAULT_FRAMING = (
    "Expand on this insight — walk me through the evidence and implications."
)
_MAX_QUOTE_CHARS = 6000


@dataclass(frozen=True)
class HandoffComposeInput:
    source_chat_title: str
    message_index: int
    quote: str
    framing_question: str | None = None
    prior_user_question: str | None = None


@dataclass(frozen=True)
class HandoffComposeResult:
    title: str
    focus_summary: str
    claims_to_ground: list[str]
    seed_prompt: str
    composed: bool
    model: str | None = None
    fallback_reason: str | None = None


def mechanical_handoff_seed(payload: HandoffComposeInput) -> HandoffComposeResult:
    """Build the legacy deterministic seed when local curation is unavailable."""
    question = (payload.framing_question or "").strip() or _DEFAULT_FRAMING
    quoted = (payload.quote or "").strip()
    blockquote = quoted.replace("\n", "\n> ")
    title = _title_from_quote(quoted)
    focus = quoted[:220] + ("…" if len(quoted) > 220 else "")
    body = (
        "I'm exploring one insight from a prior Capture Chat thread. Use workspace "
        "retrieval to ground RFP facts; treat the quoted passage as context from the "
        "prior answer, not as solicitation text.\n\n"
    )
    body += (
        f"**Source chat:** {payload.source_chat_title or 'Prior chat'} · "
        f"assistant message #{payload.message_index + 1}\n"
    )
    if payload.prior_user_question:
        body += f"**Original question:** {payload.prior_user_question.strip()}\n"
    body += f"\n**Quoted insight:**\n> {blockquote}\n\n**My question:** {question}"
    return HandoffComposeResult(
        title=title,
        focus_summary=focus,
        claims_to_ground=[],
        seed_prompt=body,
        composed=False,
        fallback_reason="mechanical",
    )


def _title_from_quote(quote: str) -> str:
    plain = re.sub(r"\s+", " ", (quote or "").strip())
    if not plain:
        return "Insight thread"
    return plain[:48] + ("…" if len(plain) > 48 else "")


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_compose_json(raw: str, payload: HandoffComposeInput) -> HandoffComposeResult:
    parsed = json.loads(_strip_json_fence(raw))
    if not isinstance(parsed, dict):
        raise ValueError("compose payload is not an object")
    title = str(parsed.get("title") or "").strip() or _title_from_quote(payload.quote)
    focus_summary = str(parsed.get("focus_summary") or "").strip()
    seed_prompt = str(parsed.get("seed_prompt") or "").strip()
    claims_raw = parsed.get("claims_to_ground") or parsed.get("claims") or []
    claims: list[str] = []
    if isinstance(claims_raw, list):
        claims = [str(item).strip() for item in claims_raw if str(item).strip()]
    if not seed_prompt:
        raise ValueError("compose payload missing seed_prompt")
    if len(title) > 120:
        title = title[:117] + "…"
    return HandoffComposeResult(
        title=title,
        focus_summary=focus_summary,
        claims_to_ground=claims[:8],
        seed_prompt=seed_prompt,
        composed=True,
    )


def _compose_system_prompt() -> str:
    return (
        "You package assistant insights for a government contracting capture workbench. "
        "Given a quoted assistant passage from a prior chat, produce a compact handoff "
        "seed for a NEW grounded chat. The new chat will use workspace retrieval (RAG) — "
        "do not invent solicitation facts. Return strict JSON only with keys: "
        "title (<=48 chars), focus_summary (1-2 sentences), claims_to_ground "
        "(array of 2-5 short verifiable claims to check against the workspace), "
        "seed_prompt (markdown user message for the new chat). The seed must: "
        "(1) state the passage is prior-answer context not RFP text, "
        "(2) include the quoted insight as a blockquote, "
        "(3) include the user's framing question, "
        "(4) ask the assistant to ground claims in workspace evidence with citations."
    )


def _compose_user_prompt(payload: HandoffComposeInput) -> str:
    quote = (payload.quote or "").strip()[:_MAX_QUOTE_CHARS]
    question = (payload.framing_question or "").strip() or _DEFAULT_FRAMING
    prior = (payload.prior_user_question or "").strip()
    lines = [
        f"Source chat title: {payload.source_chat_title or 'Prior chat'}",
        f"Assistant message index: {payload.message_index + 1}",
        f"Framing question: {question}",
    ]
    if prior:
        lines.append(f"Original user question: {prior}")
    lines.append("Quoted insight:")
    lines.append(quote)
    return "\n".join(lines)


async def compose_insight_handoff(
    payload: HandoffComposeInput,
    *,
    settings: Any,
) -> HandoffComposeResult:
    """Pack an insight handoff via local Ollama; raises when Ollama is unavailable."""
    if not is_ollama_available(settings):
        raise RuntimeError("Ollama is not reachable")
    model = resolve_ollama_model(settings)
    raw = await ollama_chat(
        [
            {"role": "system", "content": _compose_system_prompt()},
            {"role": "user", "content": _compose_user_prompt(payload)},
        ],
        settings=settings,
        model=model,
        max_tokens=1400,
        timeout=60.0,
    )
    try:
        parsed = _parse_compose_json(raw, payload)
        return HandoffComposeResult(
            title=parsed.title,
            focus_summary=parsed.focus_summary,
            claims_to_ground=parsed.claims_to_ground,
            seed_prompt=parsed.seed_prompt,
            composed=True,
            model=model,
        )
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        fallback = mechanical_handoff_seed(payload)
        return HandoffComposeResult(
            title=fallback.title,
            focus_summary=fallback.focus_summary,
            claims_to_ground=fallback.claims_to_ground,
            seed_prompt=fallback.seed_prompt,
            composed=False,
            model=model,
            fallback_reason=f"parse_error:{exc}",
        )