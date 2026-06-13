"""Shared skill-invocation retrieval and briefing-book assembly."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Optional

# slice_fn signature mirrors build_skill_briefing_book for test injection.

from src.skills.context import build_skill_briefing_book, retrieve_relevant_entities_for_skill
from src.skills.retrieval_plan import (
    SkillRetrievalPlan,
    resolve_skill_retrieval_plan,
    retrieval_metadata_from_plan,
)

QueryDataFunc = Callable[[str, str, list[dict], dict], Awaitable[dict]]
RetrieveFunc = Callable[
    [Optional[QueryDataFunc], str, str, str, dict[str, Any]],
    Awaitable[dict[str, Any]],
]

_LEGACY_PAYLOAD_TO_QUERY_KEYS = {
    "retrieval_mode": "mode",
    "retrieval_top_k": "top_k",
    "max_entities_per_type": "skill_max_entities_per_type",
    "max_chunks_per_entity": "skill_max_chunks_per_entity",
    "max_relationships_per_entity": "skill_max_relationships_per_entity",
}


def payload_to_query_overrides(payload: Any) -> dict[str, Any]:
    """Map optional per-request skill payload fields onto query settings keys."""
    overrides: dict[str, Any] = {}
    if payload is None:
        return overrides
    for payload_key, query_key in _LEGACY_PAYLOAD_TO_QUERY_KEYS.items():
        value = getattr(payload, payload_key, None)
        if value is not None:
            overrides[query_key] = value
    return overrides


def resolve_plan_from_store(
    query_settings_store: Any,
    prompt: str,
    *,
    payload: Any = None,
    skip_coverage_boost: bool = False,
) -> SkillRetrievalPlan:
    """Build the effective retrieval plan for one skill invocation."""
    return resolve_skill_retrieval_plan(
        query_settings_store.read(),
        prompt,
        request_overrides=payload_to_query_overrides(payload),
        skip_coverage_boost=skip_coverage_boost,
    )


def skill_skips_coverage_boost(skill: Any) -> bool:
    """Research-harness skills enforce their own retrieval depth — no catalog boost."""
    if skill is None:
        return False
    meta = getattr(getattr(skill, "frontmatter", None), "metadata", None) or {}
    raw = meta.get("research_harness")
    if raw is False or str(raw).strip().lower() in {"0", "false", "no", "off"}:
        return False
    if raw is True or str(raw).strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return isinstance(raw, dict)


def build_briefing_context(
    workspace_dir: Path,
    *,
    plan: SkillRetrievalPlan,
    retrieval: Mapping[str, Any],
    entity_types: Optional[list[str]] = None,
    extras: Optional[dict[str, Any]] = None,
    slice_fn: Callable[..., dict[str, Any]] = build_skill_briefing_book,
) -> dict[str, Any]:
    """Assemble the legacy/tools seed briefing book from retrieval output."""
    context = slice_fn(
        workspace_dir,
        entity_types,
        plan.briefing.max_entities_per_type,
        plan.briefing.max_chunks_per_entity,
        plan.briefing.max_relationships_per_entity,
        retrieval.get("names") or None,
        retrieval.get("chunk_ids") or None,
        plan.briefing.max_chunk_content_chars,
    )
    context["retrieval_metadata"] = retrieval_metadata_from_plan(
        plan,
        retrieval_result=retrieval,
    )
    if extras:
        context.update(extras)
    return context


def make_slice_fn(
    workspace_dir: Path,
    *,
    plan: SkillRetrievalPlan,
    retrieval_chunk_ids: Optional[set[str]] = None,
    slice_fn: Callable[..., dict[str, Any]] = build_skill_briefing_book,
) -> Callable[..., dict[str, Any]]:
    """Return a tools-mode slice function bound to the active plan."""

    def _slice(
        entity_types: Optional[list[str]],
        max_per_type: int,
        max_chunks_per_entity: int = 2,
        max_relationships_per_entity: int = 5,
        relevant_entity_names: Optional[set[str]] = None,
    ) -> dict[str, Any]:
        return slice_fn(
            workspace_dir,
            entity_types,
            min(max_per_type, plan.briefing.max_entities_per_type),
            min(max_chunks_per_entity, plan.briefing.max_chunks_per_entity),
            min(max_relationships_per_entity, plan.briefing.max_relationships_per_entity),
            relevant_entity_names,
            retrieval_chunk_ids,
            plan.briefing.max_chunk_content_chars,
        )

    return _slice


def make_retrieve_fn(
    data_func: Optional[QueryDataFunc],
    *,
    plan: SkillRetrievalPlan,
    retrieve_impl: RetrieveFunc = retrieve_relevant_entities_for_skill,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Return a tools-mode retrieve function bound to the active plan."""

    async def _retrieve(
        prompt: str,
        skill_description: str,
        mode: str,
        top_k: int,
    ) -> dict[str, Any]:
        overrides = dict(plan.query_overrides)
        if top_k:
            overrides["top_k"] = min(int(top_k), int(overrides.get("top_k") or top_k))
        effective_mode = mode if mode in {"hybrid", "local", "global", "naive", "mix"} else plan.mode
        return await retrieve_impl(
            data_func,
            prompt,
            skill_description,
            mode=effective_mode,
            query_overrides=overrides,
        )

    return _retrieve