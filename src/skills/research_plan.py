"""Methodical retrieval plan — purposeful kg passes, redundancy guards, plan completion."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from src.skills.evidence_gates import SATURATION_STRIKES_REQUIRED
from src.skills.tool_types import ToolResult

_SURFACE_TERMINAL = frozenset({"retrieved", "saturated"})
_QUERY_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
_DUPLICATE_QUERY_OVERLAP = 0.72
_EVAL_ENTITY_TYPES = frozenset({"evaluation_factor", "subfactor"})


def normalize_query_tokens(query: str) -> set[str]:
    return set(_QUERY_TOKEN_RE.findall((query or "").lower()))


def query_overlap(left: str, right: str) -> float:
    left_tokens = normalize_query_tokens(left)
    right_tokens = normalize_query_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def is_duplicate_query(query: str, prior_queries: list[str]) -> bool:
    for prior in prior_queries:
        if query_overlap(query, prior) >= _DUPLICATE_QUERY_OVERLAP:
            return True
    return False


def match_surface_id(query: str, surfaces: list[dict[str, Any]]) -> Optional[str]:
    tokens = normalize_query_tokens(query)
    best_id: Optional[str] = None
    best_score = 0
    for surface in surfaces:
        if not isinstance(surface, dict):
            continue
        keyword_tokens: set[str] = set()
        for keyword in surface.get("keywords") or []:
            keyword_tokens.update(normalize_query_tokens(str(keyword)))
        if not keyword_tokens:
            continue
        score = len(tokens & keyword_tokens)
        if score > best_score:
            best_score = score
            best_id = str(surface.get("id") or "")
    return best_id if best_score > 0 else None


def _surface_by_id(surfaces: list[dict[str, Any]], surface_id: str) -> Optional[dict[str, Any]]:
    for surface in surfaces:
        if isinstance(surface, dict) and str(surface.get("id") or "") == surface_id:
            return surface
    return None


def update_surface_after_kg_chunks(
    state: dict[str, Any],
    *,
    query: str,
    new_chunk_count: int,
) -> None:
    surfaces = state.get("plan_surfaces")
    if not isinstance(surfaces, list):
        return
    surface_id = match_surface_id(query, surfaces)
    if not surface_id:
        return
    surface = _surface_by_id(surfaces, surface_id)
    if surface is None:
        return
    attempts = int(surface.get("kg_chunks_attempts") or 0) + 1
    surface["kg_chunks_attempts"] = attempts
    surface["last_new_chunks"] = int(new_chunk_count)
    if new_chunk_count > 0:
        surface["status"] = "retrieved"
        surface["zero_chunk_strikes"] = 0
    else:
        strikes = int(surface.get("zero_chunk_strikes") or 0) + 1
        surface["zero_chunk_strikes"] = strikes
        if strikes >= SATURATION_STRIKES_REQUIRED:
            surface["status"] = "saturated"


def auto_saturate_stalled_surfaces(state: dict[str, Any]) -> int:
    """Mark pending surfaces that already ran with zero new chunks as saturated."""
    saturated = 0
    for surface in state.get("plan_surfaces") or []:
        if not isinstance(surface, dict):
            continue
        if str(surface.get("status") or "pending") != "pending":
            continue
        attempts = int(surface.get("kg_chunks_attempts") or 0)
        last_new = int(surface.get("last_new_chunks") or 0)
        if attempts >= 1 and last_new <= 0:
            surface["status"] = "saturated"
            saturated += 1
    return saturated


def close_retrieval_plan(run_dir: Path) -> bool:
    """Saturate stalled surfaces and sync retrieval_plan.json before synthesis."""
    from src.skills.research_harness import load_harness_state, save_harness_state

    state = load_harness_state(run_dir)
    if not state:
        return False
    auto_saturate_stalled_surfaces(state)
    if retrieval_plan_complete(state):
        state["phase"] = "draft"
    save_harness_state(run_dir, state)
    sync_plan_file(run_dir, state)
    return retrieval_plan_complete(state)


def mark_kg_entities_satisfied(state: dict[str, Any], types: Optional[list[str]]) -> None:
    if not types:
        return
    normalized = {str(value).strip().lower() for value in types if value}
    if normalized & _EVAL_ENTITY_TYPES:
        state["kg_entities_satisfied"] = True


def retrieval_plan_complete(state: dict[str, Any]) -> bool:
    if not state:
        return False
    if not state.get("kg_entities_satisfied"):
        return False
    surfaces = state.get("plan_surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        return False
    return all(
        isinstance(surface, dict) and str(surface.get("status") or "pending") in _SURFACE_TERMINAL
        for surface in surfaces
    )


def next_retrieval_step(state: dict[str, Any]) -> dict[str, Any]:
    if not state.get("kg_entities_satisfied"):
        return {
            "step": "kg_entities",
            "reason": "Start with one full-package kg_entities slice (include evaluation_factor and subfactor).",
        }
    surfaces = state.get("plan_surfaces") or []
    for surface in surfaces:
        if not isinstance(surface, dict):
            continue
        status = str(surface.get("status") or "pending")
        if status in _SURFACE_TERMINAL:
            continue
        suggested = str(surface.get("suggested_query") or "").strip()
        label = str(surface.get("label") or surface.get("id") or "surface")
        return {
            "step": "kg_chunks",
            "surface_id": surface.get("id"),
            "label": label,
            "suggested_query": suggested,
            "reason": f"Run one focused kg_chunks pass for: {label}.",
        }
    return {
        "step": "draft",
        "reason": "Retrieval plan complete — write configured deliverables from the scratchpad.",
    }


def format_retrieval_plan_prompt(state: dict[str, Any]) -> str:
    surfaces = state.get("plan_surfaces") or []
    lines = [
        "## Retrieval plan (methodical — one purposeful pass per surface)",
        "",
        "Execute in order. Do **not** repeat a completed step or re-query a saturated surface.",
        "Live status: `artifacts/retrieval_plan.json`. Evidence auto-accumulates in `research_scratchpad.md`.",
        "",
    ]
    if not state.get("kg_entities_satisfied"):
        lines.append(
            "1. **kg_entities** — full package types (include `evaluation_factor`, `subfactor`) — **REQUIRED FIRST**"
        )
    else:
        lines.append("1. **kg_entities** — done")
    for index, surface in enumerate(surfaces, start=2):
        if not isinstance(surface, dict):
            continue
        label = str(surface.get("label") or surface.get("id") or "surface")
        status = str(surface.get("status") or "pending")
        suggested = str(surface.get("suggested_query") or "").strip()
        feeds = surface.get("feeds")
        feeds_hint = ""
        if isinstance(feeds, list) and feeds:
            feeds_hint = f" → feeds {', '.join(str(item) for item in feeds)}"
        shipley = str(surface.get("shipley") or "").strip()
        shipley_hint = f" [Shipley:{shipley}]" if shipley else ""
        if status == "retrieved":
            marker = "done (new evidence)"
        elif status == "saturated":
            marker = "done (no new chunks — do not re-query)"
        else:
            marker = "NEXT" if next_retrieval_step(state).get("surface_id") == surface.get("id") else "pending"
        query_hint = f' Query: "{suggested}"' if suggested else ""
        lines.append(
            f"{index}. **kg_chunks** — {label}{shipley_hint} — `{status}` — "
            f"{marker}{query_hint}{feeds_hint}"
        )
    lines.append("")
    lines.append(
        "When every surface is `retrieved` or `saturated`, stop retrieval and draft deliverables."
    )
    return "\n".join(lines)


def append_prior_query(state: dict[str, Any], query: str) -> None:
    prior = list(state.get("prior_queries") or [])
    text = (query or "").strip()
    if not text:
        return
    prior.append(text)
    state["prior_queries"] = prior[-40:]


def check_kg_chunks_plan(
    run_dir: Path,
    *,
    query: str,
    phase: str,
) -> Optional[ToolResult]:
    """Short-circuit redundant or out-of-plan kg_chunks calls (no VDB hit)."""
    from src.skills.research_harness import load_harness_state

    state = load_harness_state(run_dir)
    if not state or phase != "retrieve":
        return None

    if retrieval_plan_complete(state):
        return ToolResult(
            payload={
                "skipped": True,
                "reason": "retrieval_plan_complete",
                "message": (
                    "Retrieval plan is complete. Do not call kg_chunks again — "
                    "write configured deliverables from the scratchpad."
                ),
                "next_step": next_retrieval_step(state),
            },
            transcript_extra={"plan_guard": "complete"},
        )

    text = (query or "").strip()
    if not text:
        return None

    prior = [str(item) for item in (state.get("prior_queries") or []) if item]
    if is_duplicate_query(text, prior):
        step = next_retrieval_step(state)
        return ToolResult(
            payload={
                "skipped": True,
                "reason": "duplicate_query",
                "message": (
                    "This query closely matches a prior kg_chunks pass. "
                    "Use the scratchpad evidence or advance to the next planned surface."
                ),
                "next_step": step,
            },
            transcript_extra={"plan_guard": "duplicate"},
        )

    surfaces = state.get("plan_surfaces") or []
    surface_id = match_surface_id(text, surfaces) if isinstance(surfaces, list) else None
    if surface_id:
        surface = _surface_by_id(surfaces, surface_id)
        if surface:
            if str(surface.get("status") or "") == "saturated":
                step = next_retrieval_step(state)
                return ToolResult(
                    payload={
                        "skipped": True,
                        "reason": "surface_saturated",
                        "surface_id": surface_id,
                        "message": (
                            f"Surface `{surface_id}` is saturated (prior pass returned no new chunks). "
                            "Move to the next surface in the retrieval plan."
                        ),
                        "next_step": step,
                    },
                    transcript_extra={"plan_guard": "saturated"},
                )
            if (
                str(surface.get("status") or "") == "pending"
                and int(surface.get("kg_chunks_attempts") or 0) >= 1
            ):
                surface["status"] = "saturated"
                from src.skills.research_harness import save_harness_state

                save_harness_state(run_dir, state)
                sync_plan_file(run_dir, state)
                step = next_retrieval_step(state)
                return ToolResult(
                    payload={
                        "skipped": True,
                        "reason": "surface_already_attempted",
                        "surface_id": surface_id,
                        "message": (
                            f"Surface `{surface_id}` already had a kg_chunks pass with no new evidence. "
                            "Marked saturated — advance to the next surface or draft deliverables."
                        ),
                        "next_step": step,
                    },
                    transcript_extra={"plan_guard": "saturated"},
                )

    return None


def check_kg_entities_plan(run_dir: Path, *, phase: str) -> Optional[ToolResult]:
    """Allow only one satisfied kg_entities slice during retrieve phase."""
    from src.skills.research_harness import load_harness_state

    state = load_harness_state(run_dir)
    if not state or phase != "retrieve":
        return None
    if not state.get("kg_entities_satisfied"):
        return None
    if int(state.get("kg_entities_calls") or 0) < 1:
        return None
    return ToolResult(
        payload={
            "skipped": True,
            "reason": "kg_entities_complete",
            "message": (
                "kg_entities already ran with evaluation types. "
                "Proceed with planned kg_chunks passes per retrieval_plan.json."
            ),
            "next_step": next_retrieval_step(state),
        },
        transcript_extra={"plan_guard": "kg_entities_done"},
    )


def sync_plan_file(run_dir: Path, state: dict[str, Any]) -> None:
    plan_path = Path(run_dir) / "artifacts" / "retrieval_plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "complete" if retrieval_plan_complete(state) else "active",
        "plan_complete": retrieval_plan_complete(state),
        "next_step": next_retrieval_step(state),
        "surfaces": state.get("plan_surfaces"),
    }
    plan_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")