"""Workspace-size-aware Query Tuning recommendations for the Settings UI."""

from __future__ import annotations

from typing import Any, Mapping


def _tier_for_entity_count(entity_count: int) -> str:
    if entity_count < 500:
        return "small"
    if entity_count < 2000:
        return "medium"
    if entity_count < 5000:
        return "large"
    return "xlarge"


_TIER_RECOMMENDATIONS: dict[str, dict[str, int]] = {
    "small": {
        "top_k": 40,
        "chunk_top_k": 20,
        "max_total_tokens": 40_000,
        "max_entity_tokens": 6_000,
        "max_relation_tokens": 8_000,
        "skill_max_entities_per_type": 60,
        "skill_max_chunks_per_entity": 5,
        "skill_max_relationships_per_entity": 10,
        "skill_max_chunk_content_chars": 6000,
    },
    "medium": {
        "top_k": 60,
        "chunk_top_k": 30,
        "max_total_tokens": 80_000,
        "max_entity_tokens": 12_000,
        "max_relation_tokens": 16_000,
        "skill_max_entities_per_type": 100,
        "skill_max_chunks_per_entity": 8,
        "skill_max_relationships_per_entity": 15,
        "skill_max_chunk_content_chars": 8000,
    },
    "large": {
        "top_k": 80,
        "chunk_top_k": 40,
        "max_total_tokens": 120_000,
        "max_entity_tokens": 20_000,
        "max_relation_tokens": 28_000,
        "skill_max_entities_per_type": 150,
        "skill_max_chunks_per_entity": 8,
        "skill_max_relationships_per_entity": 15,
        "skill_max_chunk_content_chars": 10000,
    },
    "xlarge": {
        "top_k": 100,
        "chunk_top_k": 50,
        "max_total_tokens": 150_000,
        "max_entity_tokens": 25_000,
        "max_relation_tokens": 35_000,
        "skill_max_entities_per_type": 200,
        "skill_max_chunks_per_entity": 10,
        "skill_max_relationships_per_entity": 20,
        "skill_max_chunk_content_chars": 12000,
    },
}


def recommend_query_settings(
    *,
    entity_count: int,
    chunk_count: int = 0,
    current: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return tier, rationale, recommended values, and whether current settings differ."""
    tier = _tier_for_entity_count(max(0, int(entity_count or 0)))
    recommended = dict(_TIER_RECOMMENDATIONS[tier])
    current_map = dict(current or {})

    differs: dict[str, dict[str, Any]] = {}
    for key, value in recommended.items():
        cur = current_map.get(key)
        if cur is None:
            continue
        try:
            if int(cur) != int(value):
                differs[key] = {"current": cur, "recommended": value}
        except (TypeError, ValueError):
            if cur != value:
                differs[key] = {"current": cur, "recommended": value}

    reason = (
        f"Workspace has ~{entity_count:,} entities"
        + (f" and ~{chunk_count:,} chunks" if chunk_count else "")
        + f" ({tier} tier). "
        "Micro-skills with narrow queries use less budget per run; these values support "
        "rich retrieval without starving large packages."
    )

    return {
        "tier": tier,
        "entity_count": entity_count,
        "chunk_count": chunk_count,
        "reason": reason,
        "recommended": recommended,
        "differs": differs,
        "should_notify": bool(differs),
    }