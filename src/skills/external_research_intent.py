"""Detect when a skill run should include external web research (URLs as seeds, not limits)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Multi-word or directive phrases — generic catalog words like "technology" must not fire alone.
_EXPLICIT_OVERLAY_PHRASES = (
    "capability overlay",
    "external research",
    "vendor overlay",
    "web research",
    "web overlay",
    "can we use",
    "should we use",
    "evaluate vendor",
    "assess vendor",
    "review vendor",
    "competitor analysis",
    "incumbent analysis",
    "third-party platform",
    "saas platform",
    "software platform",
)

_VENDOR_PATTERNS = (
    re.compile(
        r"(?:company|vendor|platform|partner|firm)\s+([A-Z][A-Za-z0-9&.,'\- ]{2,60}?)"
        r"(?:\s+with|\s+and|\s+using|[,.]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b([A-Z][A-Za-z0-9&.'\-]+(?:,\s*Inc\.?| LLC| Corp\.?| Platform))\b",
    ),
)


@dataclass(frozen=True)
class ExternalResearchIntent:
    """Structured external-research routing for orchestrator chains."""

    requested: bool
    vendor_hint: str = ""
    seed_urls: tuple[str, ...] = ()
    search_queries: tuple[str, ...] = ()
    mandatory_independent_search: bool = True
    reason: str = ""


def detect_external_research_intent(prompt: str) -> ExternalResearchIntent | None:
    """Return intent when the user explicitly requests external vendor/web overlay."""
    text = str(prompt or "").strip()
    if not text:
        return None

    urls = tuple(
        dict.fromkeys(url.rstrip(".,;") for url in _URL_RE.findall(text))
    )
    text_lc = text.lower()
    explicit_phrase = any(phrase in text_lc for phrase in _EXPLICIT_OVERLAY_PHRASES)

    vendor = ""
    for pattern in _VENDOR_PATTERNS:
        match = pattern.search(text)
        if match:
            vendor = match.group(1).strip(" .,")
            break

    # Require seed URLs, a named vendor, or an explicit overlay directive — not catalog filler.
    if not urls and not vendor and not explicit_phrase:
        return None

    queries: list[str] = []
    if vendor:
        queries.append(f"{vendor} platform capabilities federal government")
        queries.append(f"{vendor} product features integration")
    if explicit_phrase and ("modernization" in text_lc or "platform" in text_lc):
        queries.append("technology modernization capabilities government contracting")

    reason_parts: list[str] = []
    if urls:
        reason_parts.append(f"{len(urls)} seed URL(s)")
    if vendor:
        reason_parts.append(f"vendor hint: {vendor}")
    if explicit_phrase:
        reason_parts.append("explicit overlay directive")

    return ExternalResearchIntent(
        requested=True,
        vendor_hint=vendor,
        seed_urls=urls,
        search_queries=tuple(dict.fromkeys(queries)),
        mandatory_independent_search=True,
        reason="; ".join(reason_parts) or "external research intent",
    )


def external_research_intent_to_dict(intent: ExternalResearchIntent | None) -> dict[str, Any]:
    if intent is None:
        return {"requested": False}
    return {
        "requested": intent.requested,
        "vendor_hint": intent.vendor_hint,
        "seed_urls": list(intent.seed_urls),
        "search_queries": list(intent.search_queries),
        "mandatory_independent_search": intent.mandatory_independent_search,
        "reason": intent.reason,
    }