"""RFP intelligence rollup routes."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.skills.run_index import SkillRunIndex

logger = logging.getLogger(__name__)

INTEL_SLICE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "overview",
        "label": "Contract overview",
        "icon": "layout-dashboard",
        "description": "Scope primer — contract type, periods, task areas, deliverables, and performance mechanisms.",
        "action": "chat",
        "prompt": (
            "Provide an overview of the scope and services for this contract. "
            "Use an educational tone in plain language; expand acronyms on first use. "
            "Stay grounded in retrieved document terminology and facts — cite with [N]. "
            "Explain structure: contract type, periods, task/service areas, major deliverables, "
            "and key performance mechanisms."
        ),
    },
    {
        "id": "sites",
        "label": "Sites & locations",
        "icon": "map-pin",
        "description": "Geographic inventory — CONUS/OCONUS clusters, site counts, and appendix patterns.",
        "action": "chat",
        "prompt": (
            "Summarize all sites and locations in scope. Organize by country, then region. "
            "Note counts where the documents support them. Identify geographic clusters, "
            "OCONUS vs CONUS concentration, and any site-specific appendix patterns. "
            "Flag data gaps. Cite every factual claim with [N]."
        ),
    },
    {
        "id": "evaluation",
        "label": "Evaluation decoder",
        "icon": "scale",
        "description": "Decode evaluation_factor entities — weights, proof expected, strong vs weak responses.",
        "action": "chat",
        "prompt": (
            "Decode all evaluation_factor and subfactor entities (UCF Section M or equivalent). "
            "For each: what the government is evaluating; stated weights or rating definitions if present; "
            "evidence or proof they expect; what a strong vs weak response looks like per document language. "
            "Ground every row in [N] citations."
        ),
    },
    {
        "id": "mission-readiness",
        "label": "Mission Readiness Frame",
        "icon": "target",
        "description": (
            "Program-office priorities from the full solicitation package — readiness outcome, "
            "pain points, and win-theme candidates."
        ),
        "action": "skill",
        "skill": "mission-readiness-framer",
        "skill_prompt": (
            "Build the Mission Readiness Frame from the full solicitation package "
            "(PWS/SOW, background, QASP, deliverables, evaluation criteria, amendments). "
            "The program office is the customer; the contract is workload that enables readiness. "
            "Emit mission_readiness_frame, customer pain points, importance signals, "
            "implicit criteria with alternate reads, and win-theme candidates — all cited."
        ),
        "related_skills": [
            {
                "skill": "compliance-auditor",
                "label": "Acquisition traps",
                "prompt": (
                    "Forensic focus: FAR clause traps, Section L/M compliance gaps, "
                    "and contracts-shop errors — not program-office readiness."
                ),
            },
        ],
    },
    {
        "id": "financial",
        "label": "Financial risk",
        "icon": "banknote",
        "description": "Payment terms, CLIN cash flow, and capital/inventory obligations (forensic skills).",
        "action": "skill",
        "skill": "payment-terms-auditor",
        "skill_prompt": (
            "Forensic focus: payment terms and cash-flow timing by CLIN. "
            "Require verbatim extracts, a CLIN cash-flow table, H/M/L risks, and BOE implications."
        ),
        "related_skills": [
            {
                "skill": "capital-obligations-auditor",
                "label": "Capital obligations",
                "prompt": (
                    "Forensic focus: upfront capital, inventory ownership, disposition, "
                    "and transition property obligations."
                ),
            }
        ],
    },
    {
        "id": "logistics",
        "label": "Logistics SLAs",
        "icon": "truck",
        "description": "Shipping destinations, OTD/FR metrics, and surge logistics performance standards.",
        "action": "skill",
        "skill": "logistics-sla-auditor",
        "skill_prompt": (
            "Forensic focus: shipping destinations, on-time delivery, fill rate, "
            "and surge logistics SLAs. Require verbatim extracts and H/M/L risks."
        ),
    },
]

def now_iso() -> str:
    """Return compact UTC timestamp for UI rollups."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_vdb(workspace_dir: Path, name: str) -> list[dict[str, Any]]:
    """Load vdb_*.json file data array, returning [] on failure."""
    path = workspace_dir / name
    try:
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw.get("data") or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed reading %s: %s", path, exc)
        return []


def split_keywords(value: Any) -> list[str]:
    """Relationship keywords can be list or comma/space-joined string."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if item]
    return [
        token.strip().upper()
        for token in re.split(r"[,\s]+", str(value))
        if token.strip()
    ]


def compute_intel(
    workspace_dir: Path,
    *,
    generated_at: Callable[[], str] = now_iso,
) -> dict[str, Any]:
    """Build RFP intelligence rollup from workspace VDB JSON stores."""
    entities = load_vdb(workspace_dir, "vdb_entities.json")
    relations = load_vdb(workspace_dir, "vdb_relationships.json")

    by_name: dict[str, dict[str, Any]] = {}
    for entity in entities:
        name = (
            entity.get("entity_name")
            or entity.get("entity_id")
            or entity.get("__id__")
        )
        if not name:
            continue
        by_name[str(name).strip()] = entity

    buckets: dict[str, list[str]] = {}
    for name, entity in by_name.items():
        entity_type = (entity.get("entity_type") or "concept").lower()
        buckets.setdefault(entity_type, []).append(name)

    out_edges: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    in_edges: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for relation in relations:
        source = relation.get("src_id")
        target = relation.get("tgt_id")
        if not source or not target:
            continue
        types = split_keywords(
            relation.get("keywords") or relation.get("relationship_type")
        )
        for relationship_type in types:
            out_edges.setdefault(source, []).append((relationship_type, target, relation))
            in_edges.setdefault(target, []).append((relationship_type, source, relation))

    def outgoing(name: str, relationship_type: str) -> list[str]:
        return [
            target
            for edge_type, target, _ in out_edges.get(name, [])
            if edge_type == relationship_type
        ]

    def incoming(name: str, relationship_type: str) -> list[str]:
        return [
            source
            for edge_type, source, _ in in_edges.get(name, [])
            if edge_type == relationship_type
        ]

    def summarize(name: str, max_chars: int = 110) -> dict[str, Any]:
        entity = by_name.get(name) or {}
        description = (
            entity.get("description") or entity.get("content") or ""
        ).strip().replace("\n", " ")
        return {
            "id": name,
            "type": (entity.get("entity_type") or "concept").lower(),
            "description": (
                description[:max_chars] + "…"
                if len(description) > max_chars
                else description
            ),
        }

    lm_rows: list[dict[str, Any]] = []
    for instruction in sorted(buckets.get("proposal_instruction", [])):
        guided = sorted(
            set(
                outgoing(instruction, "GUIDES")
                + outgoing(instruction, "EVALUATED_BY")
            )
        )
        lm_rows.append(
            {
                "instruction": summarize(instruction),
                "factors": [summarize(factor) for factor in guided],
                "covered": bool(guided),
            }
        )

    factor_names = sorted(
        set(buckets.get("evaluation_factor", []) + buckets.get("subfactor", []))
    )
    factor_rows: list[dict[str, Any]] = []
    for factor in factor_names:
        guides = sorted(
            set(incoming(factor, "GUIDES") + incoming(factor, "EVALUATED_BY"))
        )
        factor_rows.append(
            {
                "factor": summarize(factor),
                "instructions": [summarize(instruction) for instruction in guides],
                "covered": bool(guides),
            }
        )

    trace_rows: list[dict[str, Any]] = []
    for requirement in sorted(buckets.get("requirement", [])):
        deliverables = sorted(set(outgoing(requirement, "SATISFIED_BY")))
        if not deliverables:
            trace_rows.append(
                {
                    "requirement": summarize(requirement),
                    "deliverables": [],
                    "standards": [],
                    "metrics": [],
                    "complete": False,
                }
            )
            continue
        for deliverable in deliverables:
            standards = sorted(set(outgoing(deliverable, "MEASURED_BY")))
            metrics = sorted(
                set(
                    outgoing(deliverable, "TRACKED_BY")
                    + outgoing(deliverable, "QUANTIFIES")
                )
            )
            trace_rows.append(
                {
                    "requirement": summarize(requirement),
                    "deliverables": [summarize(deliverable)],
                    "standards": [summarize(standard) for standard in standards],
                    "metrics": [summarize(metric) for metric in metrics],
                    "complete": bool(standards or metrics),
                }
            )

    coverage_rows: list[dict[str, Any]] = []
    for factor in sorted(buckets.get("evaluation_factor", [])):
        subfactors = sorted(
            set(outgoing(factor, "HAS_SUBFACTOR") + outgoing(factor, "CHILD_OF"))
        )
        instructions = sorted(set(incoming(factor, "GUIDES")))
        evidence: set[str] = set()
        for relationship_type in ("SUPPORTS", "EVIDENCES", "ADDRESSES"):
            evidence.update(incoming(factor, relationship_type))
        score = (
            (1 if instructions else 0)
            + (1 if subfactors else 0)
            + (1 if evidence else 0)
        )
        coverage_rows.append(
            {
                "factor": summarize(factor),
                "subfactor_count": len(subfactors),
                "instruction_count": len(instructions),
                "evidence_count": len(evidence),
                "score": score,
            }
        )

    gaps_req = [
        summarize(requirement)
        for requirement in sorted(buckets.get("requirement", []))
        if not outgoing(requirement, "SATISFIED_BY")
    ]
    gaps_factor = [
        summarize(factor)
        for factor in factor_names
        if not (incoming(factor, "GUIDES") or incoming(factor, "EVALUATED_BY"))
    ]
    gaps_deliverable = [
        summarize(deliverable)
        for deliverable in sorted(buckets.get("deliverable", []))
        if not (
            outgoing(deliverable, "MEASURED_BY")
            or outgoing(deliverable, "TRACKED_BY")
        )
    ]

    return {
        "generated_at": generated_at(),
        "totals": {
            "entities": len(by_name),
            "relationships": len(relations),
            "by_type": {
                key: len(value)
                for key, value in sorted(
                    buckets.items(),
                    key=lambda item: -len(item[1]),
                )
            },
        },
        "lm_matrix": {
            "instructions": lm_rows,
            "factors": factor_rows,
        },
        "traceability": trace_rows,
        "coverage": coverage_rows,
        "gaps": {
            "requirements_no_satisfaction": gaps_req,
            "factors_no_instruction": gaps_factor,
            "deliverables_no_measure": gaps_deliverable,
        },
    }


def _latest_skill_run(workspace_dir: Path, skill_name: str) -> dict[str, Any] | None:
    """Return the most recent persisted run summary for one skill, if any."""
    index = SkillRunIndex(workspace_dir / "skill_runs")
    runs = index.list_runs(skill_name=skill_name, limit=1)
    if not runs:
        return None
    run = runs[0]
    return {
        "run_id": run.get("run_id"),
        "skill": run.get("skill") or skill_name,
        "created_at": run.get("created_at"),
        "elapsed_ms": run.get("elapsed_ms"),
        "finish_reason": run.get("finish_reason"),
        "prompt_preview": run.get("prompt_preview"),
    }


def build_intel_slices(workspace_dir: Path) -> list[dict[str, Any]]:
    """Attach latest run metadata to each catalogued intelligence slice."""
    slices: list[dict[str, Any]] = []
    for entry in INTEL_SLICE_CATALOG:
        item = dict(entry)
        if item.get("action") == "skill" and item.get("skill"):
            item["latest_run"] = _latest_skill_run(workspace_dir, str(item["skill"]))
            related = []
            for rel in item.get("related_skills") or []:
                if not isinstance(rel, dict) or not rel.get("skill"):
                    continue
                related.append(
                    {
                        **rel,
                        "latest_run": _latest_skill_run(
                            workspace_dir, str(rel["skill"])
                        ),
                    }
                )
            item["related_skills"] = related
        else:
            item["latest_run"] = None
        slices.append(item)
    return slices


def register_intelligence_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
) -> None:
    """Register RFP intelligence routes for Theseus UI."""

    @app.get("/api/ui/intel/summary", tags=["theseus-ui"])
    async def intel_summary() -> JSONResponse:
        """Compute L↔M matrix, traceability chains, factor coverage, and gaps."""
        return JSONResponse(compute_intel(workspace_dir()))

    @app.get("/api/ui/intel/slices", tags=["theseus-ui"])
    async def intel_slices() -> JSONResponse:
        """Return briefing slice catalog with latest skill-run status per slice."""
        return JSONResponse({"slices": build_intel_slices(workspace_dir())})

