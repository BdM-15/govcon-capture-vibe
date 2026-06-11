"""Detect exhaustive-coverage skill prompts and widen retrieval for one run."""

from __future__ import annotations

import re
from typing import Any

# Workspace-agnostic scope signals — no customer, agency, or format names.
_EXHAUSTIVE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bfull\b.{0,40}\b(map|mapping|crosswalk|matrix|inventory|listing|overview)\b",
        r"\ball\b.{0,40}\b(task\s*areas?|requirements?|factors?|clins?|sections?|elements?)\b",
        r"\bcomplete\b.{0,40}\b(crosswalk|traceability|mapping|coverage|inventory)\b",
        r"\bentire\b.{0,40}\b(solicitation|workspace|scope|document|package)\b",
        r"\bcomprehensive\b.{0,40}\b(map|view|analysis|summary|inventory)\b",
        r"\bevery\b.{0,40}\b(task\s*area|requirement|factor|instruction|element)\b",
        r"\bwhole\b.{0,30}\b(solicitation|workspace|scope)\b",
        r"\bexhaustive\b.{0,30}\b(coverage|map|review|analysis)\b",
        r"\bmap\b.{0,20}\b(all|every|entire|full)\b",
        r"\bfull\b.{0,40}\b(solicitation|package)\b",
        r"\bmission\s+readiness\s+frame\b",
    )
)

_BOOST_MULTIPLIER = 1.75
_INT_CEILINGS: dict[str, int] = {
    "top_k": 500,
    "chunk_top_k": 500,
    "max_entity_tokens": 200_000,
    "max_relation_tokens": 200_000,
    "max_total_tokens": 500_000,
    "skill_max_entities_per_type": 500,
    "skill_max_chunks_per_entity": 50,
    "skill_max_relationships_per_entity": 50,
    "skill_max_chunk_content_chars": 50_000,
}


def detect_exhaustive_coverage_intent(prompt: str) -> bool:
    """Return True when the user prompt asks for workspace-wide coverage."""
    text = (prompt or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in _EXHAUSTIVE_PATTERNS)


def _boost_int(value: Any, *, key: str) -> int:
    ceiling = _INT_CEILINGS.get(key, 500_000)
    try:
        base = int(value)
    except (TypeError, ValueError):
        return ceiling
    boosted = int(round(base * _BOOST_MULTIPLIER))
    return max(1, min(boosted, ceiling))


def apply_coverage_boost(settings: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return widened settings plus metadata describing the one-run boost."""
    boosted = dict(settings)
    for key in (
        "top_k",
        "chunk_top_k",
        "max_entity_tokens",
        "max_relation_tokens",
        "max_total_tokens",
        "skill_max_entities_per_type",
        "skill_max_chunks_per_entity",
        "skill_max_relationships_per_entity",
        "skill_max_chunk_content_chars",
    ):
        if key in boosted:
            boosted[key] = _boost_int(boosted[key], key=key)

    metadata = {
        "coverage_boost_applied": True,
        "coverage_boost_multiplier": _BOOST_MULTIPLIER,
        "coverage_boost_reason": "exhaustive_coverage_intent",
    }
    return boosted, metadata