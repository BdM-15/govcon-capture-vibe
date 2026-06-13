"""Resolve per-run skill retrieval from workspace Query Tuning settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from src.skills.coverage_boost import apply_coverage_boost, detect_exhaustive_coverage_intent

SKILL_BRIEFING_SETTING_KEYS = (
    "skill_max_entities_per_type",
    "skill_max_chunks_per_entity",
    "skill_max_relationships_per_entity",
    "skill_max_chunk_content_chars",
)

LIGHT_RAG_OVERRIDE_KEYS = (
    "top_k",
    "chunk_top_k",
    "max_entity_tokens",
    "max_relation_tokens",
    "max_total_tokens",
    "enable_rerank",
    "only_need_context",
    "only_need_prompt",
    "response_type",
    "user_prompt",
)


@dataclass(frozen=True)
class SkillBriefingLimits:
    max_entities_per_type: int
    max_chunks_per_entity: int
    max_relationships_per_entity: int
    max_chunk_content_chars: int


@dataclass(frozen=True)
class SkillRetrievalPlan:
    mode: str
    query_overrides: dict[str, Any]
    briefing: SkillBriefingLimits
    coverage_boost_applied: bool
    coverage_boost_reason: str
    source: str = "query_settings"


def skill_retrieval_mode_from_query(query_mode: str) -> str:
    """Map Capture Chat query mode to the skill retrieval mode."""
    normalized = (query_mode or "mix").strip().lower()
    if normalized == "bypass":
        return "off"
    return normalized


def build_lightrag_overrides_from_settings(
    settings: Mapping[str, Any],
    *,
    only_need_context: bool = True,
) -> dict[str, Any]:
    """Build LightRAG QueryParam overrides from workspace query settings."""
    overrides: dict[str, Any] = {
        key: settings[key]
        for key in LIGHT_RAG_OVERRIDE_KEYS
        if key in settings and settings[key] is not None
    }
    overrides["only_need_context"] = only_need_context
    if "min_rerank_score" in settings:
        overrides["min_rerank_score"] = settings["min_rerank_score"]
    return overrides


def resolve_skill_retrieval_plan(
    settings: Mapping[str, Any],
    prompt: str,
    *,
    request_overrides: Optional[Mapping[str, Any]] = None,
    skip_coverage_boost: bool = False,
) -> SkillRetrievalPlan:
    """Merge Query Tuning settings, optional request overrides, and coverage boost."""
    effective = dict(settings)
    if request_overrides:
        for key, value in request_overrides.items():
            if value is not None:
                effective[key] = value

    coverage_boost_applied = False
    coverage_boost_reason = ""
    if not skip_coverage_boost and detect_exhaustive_coverage_intent(prompt):
        effective, boost_meta = apply_coverage_boost(effective)
        coverage_boost_applied = bool(boost_meta.get("coverage_boost_applied"))
        coverage_boost_reason = str(boost_meta.get("coverage_boost_reason") or "")

    mode = skill_retrieval_mode_from_query(str(effective.get("mode") or "mix"))
    briefing = SkillBriefingLimits(
        max_entities_per_type=int(effective.get("skill_max_entities_per_type") or 80),
        max_chunks_per_entity=int(effective.get("skill_max_chunks_per_entity") or 10),
        max_relationships_per_entity=int(
            effective.get("skill_max_relationships_per_entity") or 25
        ),
        max_chunk_content_chars=int(
            effective.get("skill_max_chunk_content_chars") or 8000
        ),
    )
    return SkillRetrievalPlan(
        mode=mode,
        query_overrides=build_lightrag_overrides_from_settings(effective),
        briefing=briefing,
        coverage_boost_applied=coverage_boost_applied,
        coverage_boost_reason=coverage_boost_reason,
    )


def retrieval_metadata_from_plan(
    plan: SkillRetrievalPlan,
    *,
    retrieval_result: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Shape retrieval metadata returned to the UI and run ledger."""
    meta = dict((retrieval_result or {}).get("metadata") or {})
    meta.update(
        {
            "mode": plan.mode,
            "top_k": plan.query_overrides.get("top_k"),
            "chunk_top_k": plan.query_overrides.get("chunk_top_k"),
            "max_total_tokens": plan.query_overrides.get("max_total_tokens"),
            "settings_source": plan.source,
            "coverage_boost_applied": plan.coverage_boost_applied,
            "coverage_boost_reason": plan.coverage_boost_reason,
            "max_entities_per_type": plan.briefing.max_entities_per_type,
            "max_chunks_per_entity": plan.briefing.max_chunks_per_entity,
            "max_relationships_per_entity": plan.briefing.max_relationships_per_entity,
            "max_chunk_content_chars": plan.briefing.max_chunk_content_chars,
        }
    )
    return meta