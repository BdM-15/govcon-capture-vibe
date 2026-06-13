"""Resolve RFP Intelligence briefing slices from the Prompt Library."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.server.briefing_prompts import BRIEFING_CHANNELS

_SKILL_PROMPT_CHANNELS = frozenset({"briefing_skill", "skill_default"})


def entry_channel(entry: dict[str, Any]) -> str:
    """Return prompt channel; plain chat starters default to ``chat``."""
    return str(entry.get("channel") or "chat").strip() or "chat"


def is_briefing_entry(entry: dict[str, Any]) -> bool:
    return entry_channel(entry) in BRIEFING_CHANNELS


def resolve_skill_default_prompt(
    prompts: list[dict[str, Any]],
    skill_name: str,
) -> dict[str, Any] | None:
    """Return the library entry bound as the default invoke prompt for a skill."""
    matches = [
        entry
        for entry in prompts
        if str(entry.get("skill") or "").strip() == skill_name
        and entry_channel(entry) in _SKILL_PROMPT_CHANNELS
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: int(item.get("sort_order") or 0))
    return matches[0]


def build_intel_slices_from_library(
    prompts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build Intel briefing slice payloads from merged prompt-library entries."""
    slices_by_id: dict[str, dict[str, Any]] = {}
    related_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for entry in prompts:
        channel = entry_channel(entry)
        if channel == "briefing_chat":
            slice_id = str(entry.get("slice_id") or "").strip()
            if not slice_id:
                continue
            slices_by_id[slice_id] = _primary_slice_from_entry(entry, action="chat")
        elif channel == "briefing_skill":
            slice_id = str(entry.get("slice_id") or "").strip()
            skill = str(entry.get("skill") or "").strip()
            if not slice_id or not skill:
                continue
            slices_by_id[slice_id] = _primary_slice_from_entry(entry, action="skill")
        elif channel == "briefing_related":
            parent_id = str(entry.get("parent_slice_id") or "").strip()
            skill = str(entry.get("skill") or "").strip()
            if not parent_id or not skill:
                continue
            related_by_parent[parent_id].append(_related_slice_from_entry(entry))

    ordered = sorted(
        slices_by_id.values(),
        key=lambda item: int(item.get("sort_order") or 0),
    )
    for item in ordered:
        slice_id = str(item.get("id") or "")
        related = sorted(
            related_by_parent.get(slice_id, []),
            key=lambda rel: int(rel.get("sort_order") or 0),
        )
        item["related_skills"] = related
    return ordered


def _primary_slice_from_entry(entry: dict[str, Any], *, action: str) -> dict[str, Any]:
    slice_id = str(entry.get("slice_id") or "").strip()
    prompt = str(entry.get("prompt") or "").strip()
    item: dict[str, Any] = {
        "id": slice_id,
        "label": str(entry.get("label") or entry.get("title") or slice_id).strip(),
        "icon": str(entry.get("icon") or "file-text").strip(),
        "description": str(entry.get("description") or "").strip(),
        "action": action,
        "sort_order": int(entry.get("sort_order") or 0),
        "prompt_library_id": str(entry.get("id") or "").strip(),
    }
    if action == "chat":
        item["prompt"] = prompt
    else:
        skill = str(entry.get("skill") or "").strip()
        item["skill"] = skill
        item["skill_prompt"] = prompt
        chain_preset = str(entry.get("chain_preset") or "").strip()
        if chain_preset:
            item["chain_preset"] = chain_preset
    return item


def _related_slice_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    skill = str(entry.get("skill") or "").strip()
    return {
        "skill": skill,
        "label": str(entry.get("label") or entry.get("title") or skill).strip(),
        "prompt": str(entry.get("prompt") or "").strip(),
        "sort_order": int(entry.get("sort_order") or 0),
        "prompt_library_id": str(entry.get("id") or "").strip(),
    }


__all__ = [
    "build_intel_slices_from_library",
    "entry_channel",
    "is_briefing_entry",
    "resolve_skill_default_prompt",
]