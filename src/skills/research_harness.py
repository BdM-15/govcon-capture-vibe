"""Research-phase harness — plan, retrieve, synthesize, reflexion (Anthropic/OpenAI/LangGraph patterns)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from src.skills.depth_gate import depth_continue_message
from src.skills.research_plan import (
    append_prior_query,
    format_retrieval_plan_prompt,
    mark_kg_entities_satisfied,
    next_retrieval_step,
    retrieval_plan_complete,
    sync_plan_file,
    update_surface_after_kg_chunks,
)
from src.skills.skill_local_tools import SkillToolsHooks
from src.skills.skill_models import Skill
from src.skills.source_citations import resolve_workspace_dir_from_run_dir

_PHASE_RETRIEVE = "retrieve"
_PHASE_DRAFT = "draft"
_PHASE_REVISE = "revise"
_PHASE_COMPLETE = "complete"

_DEFAULT_SURFACES: tuple[dict[str, Any], ...] = (
    {
        "id": "background",
        "label": "Background / mission / program-office context",
        "keywords": ["background", "mission", "program", "purpose", "objective", "pain"],
        "suggested_query": (
            "mission background program office objectives readiness outcome "
            "failure modes mission context"
        ),
        "feeds": ["readiness_outcome", "failure_modes_feared[]", "workload_enablers[]"],
    },
    {
        "id": "pws_sow",
        "label": "PWS/SOW tasks, deliverables, scope",
        "keywords": ["pws", "sow", "task", "deliverable", "statement of work", "cdrl"],
        "suggested_query": (
            "PWS SOW statement of work task areas deliverables CDRL work scope requirements"
        ),
    },
    {
        "id": "qasp",
        "label": "QASP / performance standards / SLAs",
        "keywords": ["qasp", "performance", "standard", "sla", "inspection", "metric"],
        "suggested_query": (
            "QASP performance standards inspection acceptance criteria quality metrics SLAs"
        ),
    },
    {
        "id": "evaluation",
        "label": "Evaluation factors and subfactors",
        "keywords": ["evaluation", "factor", "subfactor", "section m", "technical approach"],
        "suggested_query": (
            "evaluation factors subfactors Section M source selection technical management "
            "past performance best value"
        ),
    },
    {
        "id": "transition",
        "label": "Transition, amendments, period of performance",
        "keywords": ["transition", "amendment", "pop", "period of performance", "ramp"],
        "suggested_query": (
            "transition plan phase-in phase-out knowledge transfer amendments period of performance"
        ),
    },
)

# Mission Readiness Framer — package mechanics + mission-connection inquiry passes.
_MISSION_READINESS_SURFACES: tuple[dict[str, Any], ...] = _DEFAULT_SURFACES + (
    {
        "id": "methods_modernization",
        "label": "Modernization inquiry — current methods, systems, tooling in scope",
        "keywords": [
            "system",
            "tool",
            "software",
            "manual",
            "process",
            "digital",
            "automation",
            "legacy",
            "modernization",
            "qmss",
            "omms",
            "wawf",
            "eqms",
        ],
        "suggested_query": (
            "current methods systems tools software manual processes digital automation "
            "legacy modernization incumbent implied tooling named in PWS SOW attachments"
        ),
        "inquiry": "modernization",
        "feeds": ["current_methods[]", "workload_enablers[]"],
    },
    {
        "id": "innovation_inquiry",
        "label": "Innovation inquiry — efficiency, lean delivery, quality/cost openings",
        "keywords": [
            "innovation",
            "innovative",
            "efficient",
            "efficiency",
            "improvement",
            "continuous",
            "lean",
            "analytics",
            "predictive",
            "automation",
            "technology",
        ],
        "suggested_query": (
            "innovation innovative efficient efficiency continuous improvement lean delivery "
            "automation analytics technology quality cost reduce waste eval emphasis"
        ),
        "inquiry": "innovation",
        "feeds": ["innovation_opportunities[]", "win_theme_candidates[]"],
    },
    {
        "id": "operational_mission",
        "label": "Operational mission context — sites, surge, OCONUS, readiness metrics",
        "keywords": [
            "site",
            "location",
            "oconus",
            "conus",
            "surge",
            "shipboard",
            "readiness",
            "installation",
            "geographic",
            "place of performance",
            "operational",
        ],
        "suggested_query": (
            "sites locations OCONUS CONUS surge capacity shipboard operations installation "
            "place of performance readiness metrics workload operational constraints mission"
        ),
        "inquiry": "mission_operations",
        "feeds": ["readiness_outcome", "customer_pain_points[]", "workload_enablers[]"],
    },
    {
        "id": "tea_leaves",
        "label": "Tea leaves — importance signals, implicit criteria, hot buttons, discriminators",
        "keywords": [
            "hot button",
            "discriminator",
            "emphasis",
            "repetition",
            "priority",
            "concern",
            "risk",
            "weakness",
            "strength",
            "importance",
            "implicit",
        ],
        "suggested_query": (
            "importance signals repetition background eval echo hot button discriminator "
            "program office concerns latent structural pain threshold omission tea leaves "
            "implicit criteria acquisition read"
        ),
        "inquiry": "tea_leaves",
        "feeds": ["importance_signals[]", "implicit_criteria[]"],
    },
    {
        "id": "shipley_pains",
        "label": "Shipley — customer pains (explicit, latent, structural)",
        "keywords": [
            "pain",
            "challenge",
            "problem",
            "failure",
            "delay",
            "shortfall",
            "deficiency",
            "risk",
            "concern",
            "previous contractor",
            "audit",
            "finding",
            "surge",
            "coverage",
        ],
        "suggested_query": (
            "customer pain points program office challenges previous contractor failures "
            "audit findings transition confession latent structural pain QASP teeth "
            "threshold obsession staffing surge gap performance shortfall"
        ),
        "inquiry": "shipley_pains",
        "shipley": "capture",
        "feeds": ["customer_pain_points[]"],
    },
    {
        "id": "shipley_needs_wants",
        "label": "Shipley — customer needs, wants, priorities, buying vision",
        "keywords": [
            "need",
            "want",
            "priority",
            "objective",
            "goal",
            "outcome",
            "customer priority",
            "mission",
            "readiness",
            "benefit",
            "value",
            "buying",
        ],
        "suggested_query": (
            "customer needs wants priorities buying vision program office objectives "
            "customer priority readiness outcome what customer values mission success "
            "program office really cares about"
        ),
        "inquiry": "shipley_needs_wants",
        "shipley": "capture",
        "feeds": ["readiness_outcome", "importance_signals[]", "verbatim_extracts[]"],
    },
    {
        "id": "shipley_win_themes",
        "label": "Shipley — win themes, discriminators, hot buttons, proof hooks",
        "keywords": [
            "win theme",
            "discriminator",
            "hot button",
            "strength",
            "weakness",
            "proof",
            "differentiat",
            "outstanding",
            "confidence",
            "rating",
            "subfactor",
        ],
        "suggested_query": (
            "win theme discriminator hot button evaluation proof expected strengths "
            "weaknesses differentiators source selection best value outstanding rating "
            "what strong proposal looks like capture hooks"
        ),
        "inquiry": "shipley_win_themes",
        "shipley": "strategy",
        "feeds": ["win_theme_candidates[]", "eval_crosswalk[]"],
    },
)

_SCRATCHPAD_HEADER = (
    "# Research Scratchpad\n\n"
    "Auto-accumulated retrieval evidence for synthesis. "
    "Each pass appends verbatim excerpts and entity slices from tool results.\n"
)


@dataclass(frozen=True)
class ResearchHarnessConfig:
    """Per-skill research harness settings."""

    deliverables: tuple[str, ...] = ("brief.md",)
    frame_artifact: str = ""
    synthesis_artifact: str = "brief.md"
    coverage_contract: dict[str, Any] | None = None
    synthesis_max_tokens: int = 24_000
    reflexion_max_tokens: int = 24_000
    max_reflexion_passes: int = 2
    min_scratchpad_chars: int = 1_500
    min_kg_chunks_passes: int = 5
    scratchpad_max_chars: int = 350_000
    always_resynthesize: bool = False
    min_brief_chars: int = 0
    min_brief_lines: int = 0
    plan_surfaces: tuple[dict[str, Any], ...] = _DEFAULT_SURFACES


_FLATTENED_HARNESS_KEYS = frozenset(
    {
        "plan_surfaces",
        "plan_surfaces_path",
        "deliverables",
        "frame_artifact",
        "synthesis_artifact",
        "synthesis_max_tokens",
        "reflexion_max_tokens",
        "max_reflexion_passes",
        "always_resynthesize",
        "min_brief_chars",
        "min_brief_lines",
        "min_scratchpad_chars",
        "min_kg_chunks_passes",
        "scratchpad_max_chars",
        "coverage_contract",
    }
)


def _coverage_contract_from_flat_metadata(meta: Mapping[str, Any]) -> dict[str, Any] | None:
    """Reconstruct coverage_contract when SKILL.md nested block was flattened."""
    if not any(
        key in meta for key in ("required_entity_types", "rule", "rows_key", "artifact_path")
    ):
        return None
    contract: dict[str, Any] = {}
    for key in ("artifact_path", "required_entity_types", "rule", "rows_key"):
        if key in meta:
            contract[key] = meta[key]
    return contract or None


def _is_handoff_json_only(deliverables: tuple[str, ...]) -> bool:
    """True when every deliverable is a slice handoff JSON (no brief.md)."""
    if not deliverables:
        return False
    return all(str(item).endswith("_handoff.json") for item in deliverables)


def _is_handoff_json_frame(frame_artifact: str) -> bool:
    return bool(frame_artifact) and frame_artifact.endswith("_handoff.json")


def _material_rows_from_payload(
    payload: dict[str, Any],
    *,
    rows_key: str,
    min_rows: int,
) -> bool:
    """Return True when payload has enough substantive rows at rows_key (or nested)."""
    rows = payload.get(rows_key)
    if isinstance(rows, list) and rows:
        material = [
            row
            for row in rows
            if isinstance(row, dict) and any(str(value or "").strip() for value in row.values())
        ]
        if len(material) >= min_rows:
            return True

    for value in payload.values():
        if not isinstance(value, dict):
            continue
        nested = value.get(rows_key)
        if isinstance(nested, list) and nested:
            material = [
                row
                for row in nested
                if isinstance(row, dict) and any(str(v or "").strip() for v in row.values())
            ]
            if len(material) >= min_rows:
                return True
    return False


def _handoff_payload_has_material_content(payload: dict[str, Any]) -> bool:
    """Generic completeness check for slice handoff envelopes."""
    for key, value in payload.items():
        if key in {"claim_gaps", "source_role", "metadata"}:
            continue
        if isinstance(value, list) and value:
            if any(isinstance(row, dict) and row for row in value):
                return True
        if isinstance(value, dict):
            for subkey, subval in value.items():
                if subkey in {"claim_gaps", "metadata"}:
                    continue
                if isinstance(subval, list) and subval:
                    if any(isinstance(row, dict) and row for row in subval):
                        return True
    return False


def research_harness_overrides(meta: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize research_harness config from nested dict or flattened SKILL.md metadata."""
    raw = meta.get("research_harness")
    if isinstance(raw, dict):
        return dict(raw)
    overrides: dict[str, Any] = {
        key: meta[key] for key in _FLATTENED_HARNESS_KEYS if key in meta
    }
    coverage = overrides.get("coverage_contract")
    if not isinstance(coverage, dict):
        rebuilt = _coverage_contract_from_flat_metadata(meta)
        if rebuilt:
            overrides["coverage_contract"] = rebuilt
    return overrides


def skill_uses_research_harness(skill: Skill, hooks: SkillToolsHooks) -> bool:
    """Return True when the skill opts in or declares depth-gate hooks."""
    meta = skill.frontmatter.metadata or {}
    raw = meta.get("research_harness")
    if raw is False or str(raw).strip().lower() in {"0", "false", "no", "off"}:
        return False
    if research_harness_overrides(meta):
        return True
    if raw is True or str(raw).strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if isinstance(raw, dict):
        return True
    return hooks.validate_run is not None and hooks.artifact_continue is not None


def _load_plan_surfaces(skill: Skill, overrides: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Resolve plan surfaces from inline metadata or a skill-relative JSON path."""
    surfaces_raw = overrides.get("plan_surfaces")
    if isinstance(surfaces_raw, list) and surfaces_raw:
        return tuple(item for item in surfaces_raw if isinstance(item, dict))

    surfaces_path = str(overrides.get("plan_surfaces_path") or "").strip()
    if surfaces_path:
        file_path = (Path(skill.path) / surfaces_path).resolve()
        if file_path.is_file():
            try:
                loaded = json.loads(file_path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    return tuple(item for item in loaded if isinstance(item, dict))
            except (OSError, json.JSONDecodeError):
                pass
    return _DEFAULT_SURFACES


def resolve_harness_config(
    skill: Skill,
    entity_payload: dict[str, Any] | None = None,
) -> ResearchHarnessConfig:
    """Build harness config from skill metadata with sensible defaults."""
    meta = skill.frontmatter.metadata or {}
    overrides = research_harness_overrides(meta)
    chain_ctx = (entity_payload or {}).get("chain_step_context") or {}
    compiler_mode = str(chain_ctx.get("role") or "").strip().lower() == "compiler"

    deliverables = overrides.get("deliverables")
    if isinstance(deliverables, list) and deliverables:
        deliverable_tuple = tuple(str(item) for item in deliverables if str(item).strip())
    else:
        deliverable_tuple = ("brief.md",)

    frame = str(overrides.get("frame_artifact") or "").strip()
    if not frame and "mission_readiness_frame.json" in deliverable_tuple:
        frame = "mission_readiness_frame.json"

    synthesis = str(overrides.get("synthesis_artifact") or "brief.md").strip() or "brief.md"
    if _is_handoff_json_only(deliverable_tuple) and frame:
        synthesis = frame
    surfaces = () if compiler_mode else _load_plan_surfaces(skill, overrides)
    default_min_chunks = 0 if compiler_mode else (len(surfaces) if surfaces else 5)

    def _opt_int(key: str, default: int) -> int:
        return int(overrides.get(key) or default)

    def _opt_bool(key: str, default: bool) -> bool:
        raw_value = overrides.get(key, default)
        if isinstance(raw_value, bool):
            return raw_value
        return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}

    coverage_raw = overrides.get("coverage_contract")
    coverage_contract = dict(coverage_raw) if isinstance(coverage_raw, dict) else None

    max_reflexion_passes = _opt_int("max_reflexion_passes", 2)
    scratchpad_max_chars = int(overrides.get("scratchpad_max_chars") or 350_000)
    if compiler_mode:
        max_reflexion_passes = min(max(max_reflexion_passes, 3), 3)
        scratchpad_max_chars = max(scratchpad_max_chars, 500_000)

    return ResearchHarnessConfig(
        deliverables=deliverable_tuple,
        frame_artifact=frame,
        synthesis_artifact=synthesis,
        coverage_contract=coverage_contract,
        synthesis_max_tokens=_opt_int("synthesis_max_tokens", 24_000),
        reflexion_max_tokens=_opt_int("reflexion_max_tokens", 24_000),
        max_reflexion_passes=max_reflexion_passes,
        always_resynthesize=_opt_bool("always_resynthesize", False),
        min_brief_chars=_opt_int("min_brief_chars", 0),
        min_brief_lines=_opt_int("min_brief_lines", 0),
        min_scratchpad_chars=int(overrides.get("min_scratchpad_chars") or 1_500),
        min_kg_chunks_passes=int(
            overrides.get("min_kg_chunks_passes")
            if overrides.get("min_kg_chunks_passes") is not None
            else default_min_chunks
        ),
        scratchpad_max_chars=scratchpad_max_chars,
        plan_surfaces=surfaces,
    )


def _artifacts_dir(run_dir: Path) -> Path:
    path = Path(run_dir) / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_path(run_dir: Path) -> Path:
    return _artifacts_dir(run_dir) / "harness_state.json"


def _scratchpad_path(run_dir: Path) -> Path:
    return _artifacts_dir(run_dir) / "research_scratchpad.md"


def _plan_path(run_dir: Path) -> Path:
    return _artifacts_dir(run_dir) / "retrieval_plan.json"


def append_bootstrap_retrieval(
    run_dir: Path,
    config: ResearchHarnessConfig,
    grounded: dict[str, Any],
    *,
    query: str = "",
) -> None:
    """Seed scratchpad with full aquery_data payload before the tool loop."""
    from src.skills.researcher_retrieval import format_grounded_context_for_scratchpad

    state = load_harness_state(run_dir)
    if not state:
        return

    section = format_grounded_context_for_scratchpad(
        grounded,
        query=query,
        max_chars=min(config.scratchpad_max_chars // 2, 48_000),
    )
    scratchpad_path = _scratchpad_path(run_dir)
    existing = (
        scratchpad_path.read_text(encoding="utf-8", errors="replace")
        if scratchpad_path.is_file()
        else _SCRATCHPAD_HEADER
    )
    block = f"\n---\n\n{section}"
    updated = existing + block
    if len(updated) > config.scratchpad_max_chars:
        updated = updated[: config.scratchpad_max_chars] + "\n\n…[scratchpad truncated]\n"
    scratchpad_path.write_text(updated, encoding="utf-8")

    chunk_ids: list[str] = []
    for chunk in grounded.get("chunks") or []:
        if not isinstance(chunk, dict):
            continue
        chunk_id = str(chunk.get("chunk_id") or chunk.get("__id__") or "").strip()
        if chunk_id:
            chunk_ids.append(chunk_id)
    if chunk_ids:
        merged = list(state.get("scratchpad_chunk_ids") or []) + chunk_ids
        state["scratchpad_chunk_ids"] = merged[-5000:]

    state["scratchpad_chars"] = len(updated)
    state["bootstrap_seeded"] = True
    save_harness_state(run_dir, state)


def init_harness_state(run_dir: Path, config: ResearchHarnessConfig) -> dict[str, Any]:
    """Create harness state, scratchpad, and retrieval plan for a new run."""
    surfaces = []
    for index, item in enumerate(config.plan_surfaces, start=1):
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {
            "id": str(item.get("id") or f"surface-{index}"),
            "label": str(item.get("label") or item.get("id") or "surface"),
            "status": "pending",
            "keywords": list(item.get("keywords") or []),
            "suggested_query": str(item.get("suggested_query") or "").strip(),
            "kg_chunks_attempts": 0,
            "last_new_chunks": 0,
        }
        if item.get("inquiry"):
            entry["inquiry"] = str(item.get("inquiry"))
        if item.get("shipley"):
            entry["shipley"] = str(item.get("shipley"))
        if item.get("feeds"):
            entry["feeds"] = list(item.get("feeds"))
        surfaces.append(entry)
    state = {
        "phase": _PHASE_RETRIEVE,
        "retrieval_passes": 0,
        "scratchpad_chars": 0,
        "kg_chunks_calls": 0,
        "kg_entities_calls": 0,
        "kg_entities_satisfied": False,
        "prior_queries": [],
        "scratchpad_chunk_ids": [],
        "synthesis_ran": False,
        "reflexion_passes": 0,
        "plan_surfaces": surfaces,
    }
    _state_path(run_dir).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_plan_file(run_dir, state)
    _scratchpad_path(run_dir).write_text(_SCRATCHPAD_HEADER, encoding="utf-8")
    return state


def load_harness_state(run_dir: Path) -> dict[str, Any]:
    path = _state_path(run_dir)
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_harness_state(run_dir: Path, state: dict[str, Any]) -> None:
    _state_path(run_dir).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def get_phase(run_dir: Path) -> str:
    return str(load_harness_state(run_dir).get("phase") or _PHASE_RETRIEVE)


def set_phase(run_dir: Path, phase: str) -> None:
    state = load_harness_state(run_dir)
    if not state:
        return
    state["phase"] = phase
    save_harness_state(run_dir, state)


def _basename(path: str) -> str:
    return str(path or "").replace("\\", "/").split("/")[-1].lower()


def is_deliverable_path(path: str, config: ResearchHarnessConfig) -> bool:
    name = _basename(path)
    return name in {item.lower() for item in config.deliverables}


def validate_harness_write_file(
    run_dir: Path,
    *,
    path: str,
    config: ResearchHarnessConfig,
) -> str | None:
    """Block deliverable writes during retrieve phase (plan-and-execute gate)."""
    if not is_deliverable_path(path, config):
        return None
    phase = get_phase(run_dir)
    if phase == _PHASE_RETRIEVE:
        return (
            f"write_file blocked for {_basename(path)}: research harness is in retrieve phase. "
            "Run kg_entities (evaluation_factor + subfactor) and focused kg_chunks for each "
            "package surface until the scratchpad is substantive, then draft deliverables."
        )
    return None


def _transcript_stats(transcript: list[dict[str, Any]]) -> dict[str, int]:
    kg_chunks = 0
    kg_entities = 0
    for entry in transcript:
        if not isinstance(entry, dict) or entry.get("kind") != "tool":
            continue
        name = str(entry.get("name") or "")
        if name == "kg_chunks":
            kg_chunks += 1
        elif name == "kg_entities":
            kg_entities += 1
    return {"kg_chunks_calls": kg_chunks, "kg_entities_calls": kg_entities}


def _scratchpad_chars(run_dir: Path) -> int:
    path = _scratchpad_path(run_dir)
    if not path.is_file():
        return 0
    try:
        return len(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return 0


def build_retrieval_plan_user_addendum(run_dir: Path) -> str:
    """Return the methodical retrieval checklist injected into the user prompt."""
    state = load_harness_state(run_dir)
    if not state:
        return ""
    return format_retrieval_plan_prompt(state)


def _retrieval_gate_passed(
    run_dir: Path,
    config: ResearchHarnessConfig,
    *,
    transcript: list[dict[str, Any]] | None = None,
) -> bool:
    state = load_harness_state(run_dir)
    if not state:
        return True
    from src.skills.research_plan import auto_saturate_stalled_surfaces

    if auto_saturate_stalled_surfaces(state):
        save_harness_state(run_dir, state)
        sync_plan_file(run_dir, state)
    if retrieval_plan_complete(state):
        return True
    stats = _transcript_stats(transcript or [])
    kg_chunks = max(int(state.get("kg_chunks_calls") or 0), stats["kg_chunks_calls"])
    scratchpad = max(int(state.get("scratchpad_chars") or 0), _scratchpad_chars(run_dir))
    surfaces = state.get("plan_surfaces") or []
    terminal = sum(
        1
        for surface in surfaces
        if isinstance(surface, dict) and str(surface.get("status") or "") in {"retrieved", "saturated"}
    )
    surface_ok = terminal >= min(len(surfaces), config.min_kg_chunks_passes) if surfaces else True
    return (
        bool(state.get("kg_entities_satisfied"))
        and kg_chunks >= config.min_kg_chunks_passes
        and scratchpad >= config.min_scratchpad_chars
        and surface_ok
    )


def _format_kg_chunks_section(
    query: str,
    payload: dict[str, Any],
    cap: int,
    *,
    seen_chunk_ids: set[str] | None = None,
) -> tuple[str, list[str], int]:
    """Format scratchpad section; skip chunk bodies already captured earlier."""
    seen = seen_chunk_ids or set()
    lines = [f"### Query\n{query.strip() or '(none)'}\n"]
    names = payload.get("matched_entity_names") or []
    if names:
        lines.append("### Matched entities\n" + ", ".join(str(name) for name in names[:40]))
    grounded_entities = payload.get("grounded_entities") or []
    if isinstance(grounded_entities, list) and grounded_entities:
        lines.append("### Grounded entity details")
        for entity in grounded_entities[:25]:
            if not isinstance(entity, dict):
                continue
            name = entity.get("entity_name") or entity.get("entity_id") or entity.get("name") or ""
            desc = str(entity.get("description") or "")[:500]
            lines.append(f"- {name}: {desc}")
    grounded_relationships = payload.get("grounded_relationships") or []
    if isinstance(grounded_relationships, list) and grounded_relationships:
        lines.append("### Grounded relationships")
        for rel in grounded_relationships[:30]:
            if not isinstance(rel, dict):
                continue
            src = rel.get("src_id") or rel.get("src") or ""
            tgt = rel.get("tgt_id") or rel.get("tgt") or ""
            desc = str(rel.get("description") or rel.get("keywords") or "")[:250]
            lines.append(f"- {src} → {tgt}: {desc}")
    chunks = payload.get("source_chunks") or []
    new_ids: list[str] = []
    skipped = 0
    if isinstance(chunks, list) and chunks:
        lines.append("### Source excerpts")
        budget = cap
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or "").strip()
            content = str(chunk.get("content") or "").strip()
            if not content:
                continue
            if chunk_id and chunk_id in seen:
                skipped += 1
                continue
            if chunk_id:
                new_ids.append(chunk_id)
            from src.skills.source_citations import format_chunk_scratchpad_header

            header = (
                "\n"
                + format_chunk_scratchpad_header(
                    chunk_id=chunk_id or "chunk",
                    file_path=str(chunk.get("file_path") or ""),
                    content=content,
                )
                + "\n"
            )
            excerpt = content[: min(4000, budget)]
            budget -= len(excerpt)
            lines.append(header + excerpt)
            if budget <= 0:
                lines.append("\n…[scratchpad excerpt budget exhausted for this pass]")
                break
        if skipped:
            lines.append(
                f"\n_Skipped {skipped} chunk(s) already present in scratchpad — "
                "avoid re-querying the same surface._"
            )
    return "\n".join(lines) + "\n", new_ids, skipped


def _format_kg_entities_section(payload: dict[str, Any], cap: int) -> str:
    lines = ["### Entity slice\n"]
    entities = payload.get("entities")
    if not isinstance(entities, dict):
        return "\n".join(lines)
    budget = cap
    for entity_type, bucket in entities.items():
        if not isinstance(bucket, list) or not bucket:
            continue
        lines.append(f"\n#### {entity_type}")
        for entity in bucket[:30]:
            if not isinstance(entity, dict):
                continue
            name = str(entity.get("name") or entity.get("entity_name") or "").strip()
            description = str(entity.get("description") or "").strip()
            snippet = name
            if description:
                snippet += f" — {description[:600]}"
            lines.append(f"- {snippet[:800]}")
            budget -= len(snippet)
            if budget <= 0:
                break
        if budget <= 0:
            break
    return "\n".join(lines) + "\n"


def record_tool_retrieval(
    run_dir: Path,
    *,
    tool_name: str,
    arguments_json: str,
    payload_str: str,
    config: ResearchHarnessConfig,
) -> None:
    """Append tool retrieval results to the research scratchpad (Reflexion evidence bank)."""
    if tool_name not in {"kg_chunks", "kg_entities", "web_fetch", "web_research"}:
        return
    state = load_harness_state(run_dir)
    if not state:
        return
    try:
        payload = json.loads(payload_str) if payload_str else {}
    except json.JSONDecodeError:
        payload = {"raw": payload_str[:4000]}
    if not isinstance(payload, dict):
        payload = {"raw": str(payload)[:4000]}
    if payload.get("skipped"):
        return

    args: dict[str, Any] = {}
    try:
        parsed_args = json.loads(arguments_json or "{}")
        if isinstance(parsed_args, dict):
            args = parsed_args
    except json.JSONDecodeError:
        pass

    state["retrieval_passes"] = int(state.get("retrieval_passes") or 0) + 1
    if tool_name == "kg_chunks":
        state["kg_chunks_calls"] = int(state.get("kg_chunks_calls") or 0) + 1
        query = str(args.get("query") or "")
        append_prior_query(state, query)
        seen_raw = state.get("scratchpad_chunk_ids") or []
        seen_ids = {str(chunk_id) for chunk_id in seen_raw if chunk_id}
        section, new_ids, skipped = _format_kg_chunks_section(
            query,
            payload,
            cap=24_000,
            seen_chunk_ids=seen_ids,
        )
        update_surface_after_kg_chunks(state, query=query, new_chunk_count=len(new_ids))
        if new_ids:
            merged = list(seen_raw) + new_ids
            state["scratchpad_chunk_ids"] = merged[-5000:]
    elif tool_name == "kg_entities":
        state["kg_entities_calls"] = int(state.get("kg_entities_calls") or 0) + 1
        types = args.get("types") if isinstance(args, dict) else None
        if isinstance(types, list):
            mark_kg_entities_satisfied(state, types)
        section = _format_kg_entities_section(payload, cap=20_000)
    else:
        section = f"### {tool_name}\n```json\n{json.dumps(payload, ensure_ascii=False)[:8000]}\n```\n"

    scratchpad_path = _scratchpad_path(run_dir)
    existing = scratchpad_path.read_text(encoding="utf-8", errors="replace") if scratchpad_path.is_file() else _SCRATCHPAD_HEADER
    if len(existing) > config.scratchpad_max_chars:
        existing = existing[: config.scratchpad_max_chars] + "\n\n…[scratchpad truncated]\n"

    pass_num = int(state.get("retrieval_passes") or 1)
    block = f"\n---\n\n## Retrieval pass {pass_num} — `{tool_name}`\n\n{section}"
    updated = existing + block
    if len(updated) > config.scratchpad_max_chars:
        updated = updated[: config.scratchpad_max_chars] + "\n\n…[scratchpad truncated]\n"
    scratchpad_path.write_text(updated, encoding="utf-8")
    state["scratchpad_chars"] = len(updated)
    if retrieval_plan_complete(state):
        state["phase"] = _PHASE_DRAFT
    save_harness_state(run_dir, state)
    sync_plan_file(run_dir, state)


def _retrieve_continue_message(run_dir: Path) -> str:
    state = load_harness_state(run_dir)
    step = next_retrieval_step(state) if state else {"reason": "Follow retrieval_plan.json."}
    base = (
        "Research harness — retrieve phase. Execute the retrieval plan methodically — "
        "one purposeful pass per surface, no duplicate queries. "
        "Evidence accumulates in artifacts/research_scratchpad.md. "
    )
    if step.get("step") == "kg_entities":
        return base + step.get("reason", "")
    if step.get("step") == "kg_chunks":
        suggested = str(step.get("suggested_query") or "").strip()
        label = str(step.get("label") or "next surface")
        hint = f' Suggested query: "{suggested}"' if suggested else ""
        return base + f"Next: kg_chunks for {label}.{hint}"
    if step.get("step") == "draft":
        return (
            "Research harness — retrieval plan complete. "
            "Stop calling kg_chunks/kg_entities. Write deliverables from the scratchpad."
        )
    return base + str(step.get("reason") or "")

def _draft_continue_message(config: ResearchHarnessConfig) -> str:
    deliverables = ", ".join(f"artifacts/{name}" for name in config.deliverables)
    synthesis_note = ""
    if config.synthesis_artifact and config.synthesis_artifact in config.deliverables:
        synthesis_note = (
            f" Do NOT spend turns polishing {config.synthesis_artifact} — the platform "
            "synthesis phase generates the long-form narrative from research_scratchpad.md."
        )
    return (
        "Research harness — draft phase. Retrieval gate passed. "
        f"Write {deliverables} from the scratchpad with complete, cited content."
        f"{synthesis_note} "
        "Audit floors trigger revision only — exceed them when evidence supports more depth."
    )


def make_research_continue_fn(
    *,
    config: ResearchHarnessConfig,
    hooks: SkillToolsHooks,
    user_prompt: str = "",
    transcript_provider: Optional[Callable[[], list[dict[str, Any]]]] = None,
    chain_step_context: dict[str, Any] | None = None,
) -> Callable[[Path], Optional[str]]:
    """Compose retrieve → draft → depth-gate continuation (LangGraph conditional edge)."""

    def _continue(run_dir: Path) -> str | None:
        run_path = Path(run_dir)
        phase = get_phase(run_path)
        transcript = transcript_provider() if transcript_provider else []

        try:
            from src.skills.mission_readiness_merge import is_compiler_run_dir
        except ImportError:
            is_compiler_run_dir = lambda _path: False  # type: ignore[assignment,misc]

        if is_compiler_run_dir(run_path) and phase == _PHASE_RETRIEVE:
            set_phase(run_path, _PHASE_DRAFT)
            return (
                "Chain compiler — retrieval skipped. Expand artifacts/brief.md from merged "
                "mission_readiness_frame.json; do not call kg_chunks or kg_entities."
            )

        if phase == _PHASE_RETRIEVE:
            state = load_harness_state(run_path)
            if state and retrieval_plan_complete(state):
                set_phase(run_path, _PHASE_DRAFT)
                draft_msg = _draft_continue_message(config)
                return (
                    f"{draft_msg} "
                    "Retrieval plan complete — all package surfaces addressed."
                )
            if not _retrieval_gate_passed(run_path, config, transcript=transcript):
                return _retrieve_continue_message(run_path)

            set_phase(run_path, _PHASE_DRAFT)
            draft_msg = _draft_continue_message(config)
            return (
                f"{draft_msg} "
                "Retrieval gate passed — scratchpad is ready at "
                "artifacts/research_scratchpad.md."
            )

        depth_msg = depth_continue_message(run_path, hooks=hooks, user_prompt=user_prompt)
        if depth_msg:
            if phase == _PHASE_DRAFT:
                set_phase(run_path, _PHASE_REVISE)
            return depth_msg

        if phase == _PHASE_REVISE:
            set_phase(run_path, _PHASE_COMPLETE)
        return None

    return _continue


def _read_artifact(run_dir: Path, name: str, *, max_chars: int = 120_000) -> str:
    path = _artifacts_dir(run_dir) / name
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n…[truncated for synthesis context]\n"
    return text


def _surface_digest_for_synthesis(run_dir: Path) -> str:
    state = load_harness_state(run_dir)
    if not state:
        return ""
    lines: list[str] = []
    for surface in state.get("plan_surfaces") or []:
        if not isinstance(surface, dict):
            continue
        lines.append(
            f"- {surface.get('id')}: status={surface.get('status')} "
            f"last_new_chunks={surface.get('last_new_chunks')}"
        )
    scratchpad_chars = int(state.get("scratchpad_chars") or 0)
    if scratchpad_chars:
        lines.insert(0, f"scratchpad_chars: {scratchpad_chars}")
    return "\n".join(lines)


def build_frame_synthesis_messages(
    *,
    skill_name: str,
    skill_body: str,
    user_prompt: str,
    run_dir: Path,
    config: ResearchHarnessConfig,
) -> list[dict[str, str]]:
    """Assemble a structured JSON synthesis prompt from scratchpad evidence."""
    scratchpad = _read_artifact(run_dir, "research_scratchpad.md", max_chars=config.scratchpad_max_chars)
    frame = _read_artifact(run_dir, config.frame_artifact) if config.frame_artifact else ""
    surface_digest = _surface_digest_for_synthesis(run_dir)
    if _is_handoff_json_frame(config.frame_artifact):
        system = (
            f"You are the structured JSON synthesis phase for skill `{skill_name}` on Project Theseus.\n"
            "The retrieve phase already ran. Emit the slice handoff JSON using ONLY scratchpad evidence — "
            "no invention, no proposal prose.\n"
            f"\n## Skill contract\n{skill_body.strip()}\n"
            "\n## JSON rules (mandatory)\n"
            f"- Return ONE valid JSON object for `{config.frame_artifact}`.\n"
            "- Follow the skill contract for required top-level keys and array shapes.\n"
            "- Each array entry needs substantive fields and source_chunk_ids / cited_chunks where required.\n"
            "- source_chunk_ids must be real doc-/chunk-/tb- IDs from scratchpad — never invented labels.\n"
            "- Platform enriches source_citations[] from chunk metadata — keep source_chunk_ids accurate.\n"
            "- Log honest deferrals in claim_gaps[] — no TBD placeholders in data rows.\n"
            "- Output ONLY the JSON object (no markdown fence required).\n"
        )
    else:
        system = (
            f"You are the structured JSON synthesis phase for skill `{skill_name}` on Project Theseus.\n"
            "The retrieve phase already ran. Build the complete mission readiness envelope using ONLY "
            "scratchpad evidence — no invention.\n"
            f"\n## Skill contract\n{skill_body.strip()}\n"
            "\n## JSON rules (mandatory)\n"
            f"- Return ONE valid JSON object for `{config.frame_artifact}`.\n"
            "- Include mission_readiness_frame, opportunity_context, and every required array key.\n"
            "- eval_crosswalk: one row per material Section M factor/subfactor from scratchpad — "
            "never collapse subfactors; exclude KG meta labels (rating scales, SSDD boilerplate).\n"
            "- Each array entry needs substantive fields and source_chunk_ids where required.\n"
            "- source_chunk_ids must be real doc-/chunk-/tb- IDs from scratchpad — never invented labels.\n"
            "- Platform enriches source_citations[] from chunk metadata — keep source_chunk_ids accurate.\n"
            "- evaluation_factor must use verbatim Section M names — no capset/section-m shorthand.\n"
            "- Log honest deferrals in claim_gaps[] — no TBD placeholders in crosswalk rows.\n"
            "- Output ONLY the JSON object (no markdown fence required).\n"
        )
    user_parts = [
        "## User request\n",
        user_prompt.strip() or "(skill defaults)",
    ]
    if surface_digest:
        user_parts.extend(["\n\n## Retrieval surfaces completed\n", surface_digest])
    user_parts.extend(
        [
            "\n\n## Research scratchpad (primary evidence)\n",
            scratchpad or "(empty — quality will be poor)",
        ]
    )
    if frame.strip():
        user_parts.extend(["\n\n## Draft JSON to expand\n```json\n", frame, "\n```"])
    user_parts.append(
        f"\n\nWrite the complete `{config.frame_artifact}` JSON now. "
        "Return ONLY the JSON object."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "".join(user_parts)},
    ]


def frame_artifact_needs_work(run_dir: Path, config: ResearchHarnessConfig) -> bool:
    """True when structured frame JSON is missing or primary rows are too thin."""
    if not config.frame_artifact:
        return False
    path = _artifacts_dir(run_dir) / config.frame_artifact
    if not path.is_file():
        return True
    try:
        from src.skills.readiness_handoff_models import load_handoff_dict

        payload = load_handoff_dict(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return True

    contract = config.coverage_contract or {}
    rows_key = str(contract.get("rows_key") or "").strip()
    if rows_key:
        workspace_dir = resolve_workspace_dir_from_run_dir(run_dir)
        if rows_key == "eval_crosswalk" and workspace_dir is not None:
            from src.skills.handoff_quality import required_crosswalk_rows

            min_rows = required_crosswalk_rows(workspace_dir)
            if not _material_rows_from_payload(payload, rows_key=rows_key, min_rows=min_rows):
                return True
            from src.skills.evidence_gates import check_coverage_contract

            coverage_issues = check_coverage_contract(
                workspace_dir=workspace_dir,
                coverage_contract=contract,
                artifact=payload,
            )
            return bool(coverage_issues)
        min_rows = 3 if rows_key == "eval_crosswalk" else 1
        return not _material_rows_from_payload(payload, rows_key=rows_key, min_rows=min_rows)

    if _is_handoff_json_frame(config.frame_artifact):
        return not _handoff_payload_has_material_content(payload)

    crosswalk = payload.get("eval_crosswalk")
    if not isinstance(crosswalk, list) or not crosswalk:
        return True
    material = [
        row
        for row in crosswalk
        if isinstance(row, dict)
        and str(row.get("evaluation_factor") or "").strip()
        and len(str(row.get("readiness_link") or "").strip()) >= 40
    ]
    return len(material) < 3


def build_synthesis_messages(
    *,
    skill_name: str,
    skill_body: str,
    user_prompt: str,
    run_dir: Path,
    config: ResearchHarnessConfig,
) -> list[dict[str, str]]:
    """Assemble a long-form synthesis prompt from scratchpad + frame JSON (OpenAI deep-research style)."""
    from src.skills.mission_readiness_merge import is_compiler_run_dir

    scratchpad = _read_artifact(run_dir, "research_scratchpad.md", max_chars=config.scratchpad_max_chars)
    frame = _read_artifact(run_dir, config.frame_artifact) if config.frame_artifact else ""
    brief_scaffold = _read_artifact(run_dir, config.synthesis_artifact)
    surface_digest = _surface_digest_for_synthesis(run_dir)
    min_chars = config.min_brief_chars or 12_000
    min_lines = config.min_brief_lines or 100
    compiler_mode = is_compiler_run_dir(run_dir)
    compiler_rules = ""
    if compiler_mode:
        compiler_rules = (
            "\n## Chain compiler mode (mandatory)\n"
            "- Upstream handoffs were merged deterministically — do NOT invent new eval rows or "
            "re-run retrieval.\n"
            "- Expand the existing brief scaffold in place: keep sections 1–8 and the eval "
            "cross-walk markdown table; add multi-paragraph analytical prose under each section.\n"
            "- Mirror every claim_gaps[] entry in section 8 (Clarification Questions + Claim Gaps).\n"
            "- Expand acronyms on first use as Full Term (ACR).\n"
            "- Preserve source_chunk_ids from the merged JSON — do not substitute invented labels.\n"
            "- Cite evidence with numbered markers only — [1], [2], etc. — matching "
            "mission_readiness_frame.json references[].ref.\n"
            "- Keep the References section at document end with full source names; "
            "never inline long document titles or quotes in narrative prose.\n"
            "- Never cite handoff.json filenames or bare chunk IDs in reader-facing brief.md prose.\n"
            "- End with executive synthesis tying readiness outcome to top win themes.\n"
        )
    system = (
        f"You are the synthesis phase for skill `{skill_name}` on Project Theseus.\n"
        "The retrieve phase already ran. Use ONLY the research scratchpad and draft JSON — "
        "do not invent facts. Your job is a **research-depth capture brief**, not a summary.\n"
        f"{compiler_rules}"
        "\n## Skill contract\n"
        f"{skill_body.strip()}\n"
        "\n## Synthesis rules (mandatory depth)\n"
        + (
            f"- Output the full `{config.synthesis_artifact}` in markdown — substance over "
            "volume: verbatim quotes, per-section analysis, numbered citations.\n"
            if compiler_mode
            else f"- Output the full `{config.synthesis_artifact}` in markdown — depth audit floors "
            f"are >={min_chars} characters and >={min_lines} lines when configured; exceed them "
            "when evidence supports more.\n"
        )
        + "- **Analytical prose required:** multi-paragraph reasoning per section — what the "
        "government signal means, why the program office cares, readiness consequence, capture "
        "implication. Bullets alone are insufficient except verbatim bank and eval table.\n"
        + "- Mine **every retrieval surface** in the scratchpad — do not compress rich evidence "
        "into generic one-liners.\n"
        + (
            "- Major narrative sections: substantive multi-paragraph analysis before tables/lists.\n"
            "- Eval cross-walk (when applicable): full markdown table, one row per material "
            "Section M factor/subfactor; readiness_link = consequence analysis per row.\n"
            "- Customer pains, verbatim extracts, win themes, importance signals, and implicit "
            "criteria: cover every **material** item the package supports (audit floors apply; "
            "do not pad with placeholders).\n"
            "- Class B judgments use `Our read:`, `Likely`, `Signal:`, `In our capture experience,`.\n"
            "- Every factual claim cites numbered references only — [1], [2], etc. — using "
            "references[].ref from the merged JSON. Multiple sources: [1][3].\n"
            "- Full source names, sections, and quotes belong ONLY in the References section "
            "at document end — never inline long citations in narrative prose.\n"
            "- Never cite handoff.json filenames or bare chunk IDs in brief.md; chunk IDs are trace "
            "metadata only.\n"
            "- **Uniform depth:** back-half sections (methods/innovation, win themes, clarifications) "
            "must match front-half analytical depth — no compressed one-liner tails.\n"
            "- Mirror every `claim_gaps[]` entry in a Clarifications / missing-coverage section.\n"
            "- Do NOT add capability overlay unless the user explicitly names a vendor or URL.\n"
            "- Close with a short executive synthesis tying readiness outcome to top win themes.\n"
            "- Keep the References section as the final section of brief.md (after Executive Synthesis).\n"
        )
    )
    user_parts = [
        "## User request\n",
        user_prompt.strip() or "(skill defaults)",
    ]
    if surface_digest:
        user_parts.extend(["\n\n## Retrieval surfaces completed\n", surface_digest])
    user_parts.extend(
        [
            "\n\n## Research scratchpad (primary evidence — use exhaustively)\n",
            scratchpad or "(empty — synthesis quality will be poor)",
        ]
    )
    if frame:
        user_parts.extend(["\n\n## Draft JSON envelope\n```json\n", frame, "\n```"])
    if compiler_mode and brief_scaffold.strip():
        user_parts.extend(
            [
                "\n\n## Brief scaffold to expand (preserve headings + eval table)\n",
                brief_scaffold,
            ]
        )
    user_parts.append(
        f"\n\nWrite the complete `{config.synthesis_artifact}` now. "
        "Return ONLY the markdown document."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "".join(user_parts)},
    ]


def dedupe_depth_issues(issues: list[str]) -> list[str]:
    """Drop duplicate audit lines so reflexion focuses on distinct fixes."""
    seen: set[str] = set()
    unique: list[str] = []
    for issue in issues:
        key = str(issue or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(str(issue).strip())
    return unique


def normalize_brief_section_key(heading: str) -> str:
    text = str(heading or "").strip()
    if text.startswith("## "):
        text = text[3:]
    return text.strip().lower()


def split_brief_sections(brief_text: str) -> tuple[str, list[tuple[str, str]]]:
    """Split brief into preamble (before first ##) and ordered (heading, body) pairs."""
    preamble_lines: list[str] = []
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_body: list[str] = []
    seen_section = False
    for line in str(brief_text or "").splitlines():
        if line.startswith("## "):
            seen_section = True
            if current_heading:
                sections.append((current_heading, "\n".join(current_body).strip()))
            current_heading = line[3:].strip()
            current_body = []
            continue
        if not seen_section:
            preamble_lines.append(line)
        else:
            current_body.append(line)
    if current_heading:
        sections.append((current_heading, "\n".join(current_body).strip()))
    return "\n".join(preamble_lines).strip(), sections


def reassemble_brief_sections(preamble: str, sections: list[tuple[str, str]]) -> str:
    parts: list[str] = []
    if preamble.strip():
        parts.append(preamble.strip())
        parts.append("")
    for heading, body in sections:
        parts.append(f"## {heading}")
        parts.append("")
        if body.strip():
            parts.append(body.strip())
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def apply_section_patches_to_brief(
    brief_text: str,
    patches: list[dict[str, Any]],
) -> str:
    """Replace only named ## sections; leave all other brief content untouched."""
    preamble, sections = split_brief_sections(brief_text)
    patch_map: dict[str, str] = {}
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        heading = str(patch.get("heading") or patch.get("section") or "").strip()
        content = str(patch.get("content") or patch.get("body") or "").strip()
        if not heading or not content:
            continue
        patch_map[normalize_brief_section_key(heading)] = content

    merged_sections: list[tuple[str, str]] = []
    for heading, body in sections:
        key = normalize_brief_section_key(heading)
        merged_sections.append((heading, patch_map.get(key, body)))
    return reassemble_brief_sections(preamble, merged_sections)


def brief_section_headings(brief_text: str) -> list[str]:
    return [heading for heading, _ in split_brief_sections(brief_text)[1]]


def _count_crosswalk_table_rows(brief_text: str) -> int:
    in_table = False
    rows = 0
    for line in str(brief_text or "").splitlines():
        if re.search(
            r"^##\s*(?:\d+\.\s*)?eval(?:uation)?\s+cross[- ]?walk\b",
            line,
            re.IGNORECASE,
        ):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        if in_table and line.strip().startswith("|") and "---" not in line:
            rows += 1
    return rows


def brief_structure_preserved(
    original: str,
    merged: str,
    *,
    min_length_ratio: float = 0.85,
) -> tuple[bool, str]:
    """Reject full-doc rewrites that drop headings, shrink the brief, or lose eval rows."""
    orig_headings = brief_section_headings(original)
    merged_headings = brief_section_headings(merged)
    if orig_headings != merged_headings:
        return False, "section headings changed — compiler reflexion must patch in place"

    orig_len = len(str(original or "").strip())
    merged_len = len(str(merged or "").strip())
    if orig_len and merged_len < int(orig_len * min_length_ratio):
        return (
            False,
            f"brief shrank {orig_len} → {merged_len} chars — likely full rewrite, not patch",
        )

    orig_rows = _count_crosswalk_table_rows(original)
    merged_rows = _count_crosswalk_table_rows(merged)
    if orig_rows and merged_rows < orig_rows:
        return False, f"eval cross-walk table lost rows ({orig_rows} → {merged_rows})"

    return True, ""


def parse_compiler_section_patches(content: str) -> list[dict[str, Any]]:
    """Extract section_patches[] from compiler reflexion JSON output."""
    payload = _extract_json_object(content)
    if not payload:
        return []
    patches = payload.get("section_patches") or payload.get("patches") or []
    if not isinstance(patches, list):
        return []
    return [patch for patch in patches if isinstance(patch, dict)]


def build_compiler_reflexion_messages(
    *,
    skill_name: str,
    skill_body: str,
    user_prompt: str,
    run_dir: Path,
    config: ResearchHarnessConfig,
    issues: list[str],
) -> list[dict[str, str]]:
    """Compiler revise — expand named sections in place; no full-doc rewrite quota chase."""
    scratchpad = _read_artifact(run_dir, "research_scratchpad.md", max_chars=config.scratchpad_max_chars)
    current = _read_artifact(run_dir, config.synthesis_artifact)
    frame = _read_artifact(run_dir, config.frame_artifact) if config.frame_artifact else ""
    unique = dedupe_depth_issues(issues)
    compiler_fixable = [
        issue
        for issue in unique
        if not issue.lower().startswith("eval_crosswalk row")
        and "evaluation_factor looks like invented" not in issue.lower()
        and "over-relies on one source chunk" not in issue.lower()
    ]
    if not compiler_fixable:
        compiler_fixable = unique[:8]
    issue_text = "\n".join(f"- {issue}" for issue in compiler_fixable[:12])
    system = (
        f"You are the chain compiler revise phase for skill `{skill_name}`.\n"
        "Fix ONLY the listed issues by expanding the matching brief.md sections IN PLACE.\n"
        "- Preserve all existing headings, eval cross-walk table rows, and References.\n"
        "- Do NOT rewrite the entire document from scratch.\n"
        "- Do NOT chase character count — add substance: verbatim quotes, citations, "
        "factor-specific reasoning from scratchpad.\n"
        "- Skip eval_crosswalk row defects — upstream eval handoff owns those.\n"
        f"\n## Skill contract\n{skill_body.strip()}\n"
    )
    user = (
        f"## User request\n{user_prompt.strip()}\n\n"
        f"## Issues to fix (compiler-owned only)\n{issue_text}\n\n"
        f"## Current `{config.synthesis_artifact}` (expand in place)\n{current or '(missing)'}\n\n"
        f"## Research scratchpad\n{scratchpad[:120_000] or '(empty)'}\n\n"
    )
    if frame:
        user += f"## Merged JSON spine\n```json\n{frame[:40_000]}\n```\n\n"
    user += (
        "Return ONE JSON object only — no markdown wrapper:\n"
        '{"section_patches":[{"heading":"## N. Section Title","content":"expanded body"}]}\n'
        "- Include ONLY sections you expanded to fix the listed issues.\n"
        "- Use exact `##` headings from the current brief.\n"
        "- Do NOT return the full brief — patches merge server-side."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_reflexion_messages(
    *,
    skill_name: str,
    skill_body: str,
    user_prompt: str,
    run_dir: Path,
    config: ResearchHarnessConfig,
    issues: list[str],
) -> list[dict[str, str]]:
    """Build a Reflexion-style revise prompt grounded in audit issues + scratchpad."""
    from src.skills.mission_readiness_merge import is_compiler_run_dir

    if is_compiler_run_dir(run_dir):
        return build_compiler_reflexion_messages(
            skill_name=skill_name,
            skill_body=skill_body,
            user_prompt=user_prompt,
            run_dir=run_dir,
            config=config,
            issues=issues,
        )

    scratchpad = _read_artifact(run_dir, "research_scratchpad.md", max_chars=200_000)
    current = _read_artifact(run_dir, config.synthesis_artifact)
    frame = _read_artifact(run_dir, config.frame_artifact) if config.frame_artifact else ""
    unique = dedupe_depth_issues(issues)
    issue_text = "\n".join(f"- {issue}" for issue in unique[:20])
    min_chars = config.min_brief_chars or 12_000
    system = (
        f"You are the reflexion revise phase for skill `{skill_name}`.\n"
        "Expand and correct the deliverable to fix every depth-audit issue.\n"
        "This must be **research-depth capture analysis** — multi-paragraph reasoning per "
        "section, not bullet summaries. Maintain uniform consultant depth through the final "
        "sections; expand any compressed tail. Target "
        f">={min_chars} characters if brief is thin.\n"
        f"\n## Skill contract\n{skill_body.strip()}\n"
    )
    user = (
        f"## User request\n{user_prompt.strip()}\n\n"
        f"## Depth audit issues to fix\n{issue_text}\n\n"
        f"## Current `{config.synthesis_artifact}`\n{current or '(missing)'}\n\n"
        f"## Research scratchpad\n{scratchpad}\n\n"
    )
    if frame:
        user += f"## Draft JSON\n```json\n{frame}\n```\n\n"
    user += (
        f"Rewrite the complete `{config.synthesis_artifact}` fixing all issues. "
        "Return ONLY the full revised markdown."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def needs_synthesis(run_dir: Path, config: ResearchHarnessConfig) -> bool:
    """Return True when scratchpad is substantive but synthesis deliverable is missing/thin."""
    if config.synthesis_artifact.endswith(".json") or _is_handoff_json_only(config.deliverables):
        return False
    if _scratchpad_chars(run_dir) < config.min_scratchpad_chars:
        return False
    if config.always_resynthesize:
        return True
    text = _read_artifact(run_dir, config.synthesis_artifact)
    if not text.strip():
        return True
    stripped = text.strip()
    if config.min_brief_chars and len(stripped) < config.min_brief_chars:
        return True
    if config.min_brief_lines and len(stripped.splitlines()) < config.min_brief_lines:
        return True
    # Legacy thin brief heuristic: missing eval cross-walk heading or very short
    if len(stripped) < 2_500:
        return True
    if config.synthesis_artifact.endswith(".md"):
        if not re.search(
            r"^##\s*(?:\d+\.\s*)?eval(?:uation)?\s+cross[- ]?walk\b",
            text,
            re.IGNORECASE | re.MULTILINE,
        ):
            return True
    return False


def write_synthesis_artifact(run_dir: Path, config: ResearchHarnessConfig, content: str) -> Path:
    path = _artifacts_dir(run_dir) / config.synthesis_artifact
    path.write_text(content.strip() + "\n", encoding="utf-8")
    state = load_harness_state(run_dir)
    if state:
        state["synthesis_ran"] = True
        state["phase"] = _PHASE_COMPLETE
        save_harness_state(run_dir, state)
    return path


def _extract_json_object(content: str) -> dict[str, Any] | None:
    """Parse a JSON object from raw LLM output (fenced or bare)."""
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
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def build_frame_reflexion_messages(
    *,
    skill_name: str,
    skill_body: str,
    user_prompt: str,
    run_dir: Path,
    config: ResearchHarnessConfig,
    issues: list[str],
) -> list[dict[str, str]]:
    """Build a revise prompt that expands the structured JSON envelope from scratchpad + brief."""
    scratchpad = _read_artifact(run_dir, "research_scratchpad.md", max_chars=200_000)
    brief = _read_artifact(run_dir, config.synthesis_artifact)
    frame = _read_artifact(run_dir, config.frame_artifact) if config.frame_artifact else ""
    issue_text = "\n".join(f"- {issue}" for issue in issues[:20])
    system = (
        f"You are the structured JSON revise phase for skill `{skill_name}`.\n"
        "Expand the draft envelope using ONLY scratchpad and brief evidence — no invention.\n"
        f"\n## Skill contract\n{skill_body.strip()}\n"
        "\n## JSON rules\n"
        f"- Return ONE valid JSON object for `{config.frame_artifact}`.\n"
        "- One eval_crosswalk row per material Section M factor/subfactor — NOT KG meta labels "
        "(tradeoff methodology, SSDD, rating scales, generic 'evaluation factor').\n"
        "- Do not collapse multiple subfactors into a single factor row.\n"
        "- Diversify source_chunk_ids across rows — do not cite one chunk for half the table.\n"
        "- source_chunk_ids must be real doc-/chunk-/tb- IDs — reject invented shorthand labels.\n"
        "- Expand customer_pain_points, verbatim_extracts, win_theme_candidates, "
        "importance_signals, and implicit_criteria from scratchpad to audit-floor depth.\n"
        "- Every array entry needs substantive fields and source_chunk_ids where required.\n"
        "- Log honest deferrals in claim_gaps[] — do not pad with placeholders.\n"
        "- Output ONLY the JSON object (no markdown wrapper required).\n"
    )
    user = (
        f"## User request\n{user_prompt.strip()}\n\n"
        f"## Depth audit issues to fix\n{issue_text}\n\n"
        f"## Current `{config.synthesis_artifact}`\n{brief or '(missing)'}\n\n"
        f"## Current `{config.frame_artifact}`\n```json\n{frame or '{}'}\n```\n\n"
        f"## Research scratchpad\n{scratchpad}\n\n"
        f"Rewrite the complete `{config.frame_artifact}` JSON fixing all issues."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _validate_frame_payload(frame_artifact: str, content: str) -> str | None:
    """Run handoff validators on harness-synthesized JSON (same rules as write_file)."""
    from src.skills.readiness_content_gates import validate_eval_handoff_write

    name = Path(frame_artifact).name.lower()
    if name == "eval_handoff.json":
        return validate_eval_handoff_write(path=name, content=content)
    return None


def write_frame_artifact(
    run_dir: Path,
    config: ResearchHarnessConfig,
    content: str,
    *,
    workspace_dir: Path | None = None,
) -> Path | None:
    """Parse and persist a revised JSON frame envelope."""
    if not config.frame_artifact:
        return None
    payload = _extract_json_object(content)
    if not payload:
        return None
    resolved_workspace = workspace_dir or resolve_workspace_dir_from_run_dir(run_dir)
    if resolved_workspace is not None:
        from src.skills.source_citations import enrich_payload_citations

        payload = enrich_payload_citations(payload, resolved_workspace)

    serialized = json.dumps(payload, ensure_ascii=False)
    blocked = _validate_frame_payload(config.frame_artifact, serialized)
    if blocked:
        return None

    path = _artifacts_dir(run_dir) / config.frame_artifact
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path