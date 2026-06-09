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

logger = logging.getLogger(__name__)

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

