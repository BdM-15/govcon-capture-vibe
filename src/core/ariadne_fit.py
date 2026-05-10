"""Deterministic Requirements Fit Score for Ariadne workspaces."""

from __future__ import annotations

from typing import Any

FORMULA_VERSION = "ariadne-fit-v1"
_PURSUIT_STAGES = {"identify", "qualify", "capture", "proposal", "submitted", "award"}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _entity_points(count: int) -> int:
    if count >= 100:
        return 25
    if count >= 50:
        return 22
    if count >= 20:
        return 18
    if count > 0:
        return 12
    return 0


def _accent(score: int) -> str:
    if score >= 75:
        return "lime"
    if score >= 50:
        return "cyan"
    if score >= 25:
        return "amber"
    return "magenta"


def _stage(row: dict[str, Any]) -> str:
    pursuit = row.get("pursuit") if isinstance(row.get("pursuit"), dict) else {}
    pursuit_stage = str(pursuit.get("stage") or "").strip().lower()
    if pursuit_stage in _PURSUIT_STAGES:
        return pursuit_stage
    if not (row.get("documents") or row.get("entities") or row.get("neo4j_nodes")):
        return "intake"
    if row.get("entities") and row.get("neo4j_nodes"):
        return "knowledge-ready"
    if row.get("documents"):
        return "processing"
    return "staged"


def workspace_rows(
    *,
    workspaces: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    active_workspace: str,
) -> list[dict[str, Any]]:
    """Merge `/api/ui/workspaces` and inventory rows into dashboard rows."""
    inventory_by_name = {
        str(row.get("name") or ""): row for row in inventory if row.get("name")
    }
    workspace_by_name = {
        str(row.get("name") or ""): row for row in workspaces if row.get("name")
    }
    names = sorted(set(inventory_by_name) | set(workspace_by_name))
    rows: list[dict[str, Any]] = []
    for name in names:
        workspace = workspace_by_name.get(name, {})
        inv = inventory_by_name.get(name, {})
        rows.append(
            {
                **workspace,
                **inv,
                "name": name,
                "is_active": name == active_workspace or bool(inv.get("is_active")),
                "documents": _as_int(workspace.get("documents")),
                "entities": _as_int(workspace.get("entities")),
                "chats": _as_int(workspace.get("chats")),
                "neo4j_nodes": _as_int(inv.get("neo4j_nodes")),
                "storage_mb": inv.get("storage_mb"),
                "inputs_files": _as_int(inv.get("inputs_files")),
                "pursuit": inv.get("pursuit") if isinstance(inv.get("pursuit"), dict) else None,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            not row.get("is_active"),
            -_as_int(row.get("documents")),
            str(row.get("name") or ""),
        ),
    )


def fit_score_for_row(
    *,
    row: dict[str, Any],
    promotions: list[dict[str, Any]],
    wiki_count: int,
    active_workspace: str,
) -> dict[str, Any]:
    """Calculate one workspace Requirements Fit Score from source facts."""
    workspace = str(row.get("name") or "")
    processed_promotions = sum(
        1 for record in promotions if (record.get("ingestion_status") or "pending") == "processed"
    )
    pending_promotions = sum(
        1 for record in promotions if (record.get("ingestion_status") or "pending") != "processed"
    )
    documents = _as_int(row.get("documents"))
    entities = _as_int(row.get("entities"))
    nodes = _as_int(row.get("neo4j_nodes"))
    pursuit = row.get("pursuit") if isinstance(row.get("pursuit"), dict) else {}
    pwin = pursuit.get("pwin") if isinstance(pursuit.get("pwin"), dict) else {}
    drivers = _safe_list(pursuit.get("pwin_drivers"))
    pwin_value = pwin.get("value")
    has_pwin = isinstance(pwin_value, (int, float))
    has_gate = bool(
        (pursuit.get("gate") or {}).get("due") if isinstance(pursuit.get("gate"), dict) else None
    ) or bool(pursuit.get("proposal_due"))

    kg_points = (10 if documents else 0) + _entity_points(entities) + (10 if nodes else 0)
    promoted_points = _clamp(processed_promotions * 10 + min(pending_promotions, 2) * 3, 0, 30)
    wiki_points = _clamp(8 + wiki_count * 2, 0, 15) if wiki_count else 0
    metadata_points = (4 if has_pwin else 0) + (4 if drivers else 0) + (2 if has_gate else 0)
    score = _clamp(kg_points + promoted_points + wiki_points + metadata_points, 0, 100)

    blockers: list[str] = []
    if not documents:
        blockers.append("load solicitation docs")
    if not entities:
        blockers.append("extract KG entities")
    if not processed_promotions:
        blockers.append("refresh promoted source")
    if not wiki_count:
        blockers.append("seed capability wiki")
    if not has_pwin:
        blockers.append("set PWin")

    return {
        "workspace": workspace,
        "score": score,
        "accent": _accent(score),
        "stage": _stage(row),
        "is_active_workspace": workspace == active_workspace,
        "detail": " / ".join(blockers[:2]) if blockers else "KG, source, wiki, metadata ready",
        "blockers": blockers,
        "components": [
            {"key": "kg", "label": "KG", "value": kg_points, "max": 45},
            {"key": "sources", "label": "Sources", "value": promoted_points, "max": 30},
            {"key": "wiki", "label": "Wiki", "value": wiki_points, "max": 15},
            {"key": "meta", "label": "Meta", "value": metadata_points, "max": 10},
        ],
        "source_counts": {
            "documents": documents,
            "entities": entities,
            "neo4j_nodes": nodes,
            "promoted_processed": processed_promotions,
            "promoted_pending": pending_promotions,
            "llm_wiki": wiki_count,
            "pwin_drivers": len(drivers),
            "has_gate": has_gate,
            "has_pwin": has_pwin,
        },
        "formula_version": FORMULA_VERSION,
    }


def fit_scores(
    *,
    workspaces: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    promotions_by_workspace: dict[str, list[dict[str, Any]]],
    wiki_count: int,
    active_workspace: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Calculate sorted Requirements Fit Scores for all known workspaces."""
    scores = [
        fit_score_for_row(
            row=row,
            promotions=promotions_by_workspace.get(str(row.get("name") or ""), []),
            wiki_count=wiki_count,
            active_workspace=active_workspace,
        )
        for row in workspace_rows(
            workspaces=workspaces,
            inventory=inventory,
            active_workspace=active_workspace,
        )
    ]
    scores.sort(
        key=lambda row: (
            not row.get("is_active_workspace"),
            -_as_int(row.get("score")),
            str(row.get("workspace") or ""),
        )
    )
    return scores[:limit] if limit is not None else scores


__all__ = ["FORMULA_VERSION", "fit_score_for_row", "fit_scores", "workspace_rows"]