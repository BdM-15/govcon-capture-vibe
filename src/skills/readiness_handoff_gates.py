"""Shared substance gates for readiness-frame micro-skill handoffs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.skills.evidence_gates import (
    DEFAULT_COVERAGE_MIN_RATIO,
    check_coverage_contract,
)
from src.skills.readiness_content_gates import substance_issues_for_crosswalk
from src.skills.readiness_handoff_models import (
    TeaLeavesHandoff,
    load_handoff_dict,
    validate_handoff_file,
)
from src.skills.source_citations import resolve_workspace_dir_from_run_dir

EVAL_COVERAGE_CONTRACT = {
    "artifact_path": "eval_handoff.json",
    "required_entity_types": ["evaluation_factor", "subfactor"],
    "rule": "one_row_per_entity",
    "rows_key": "eval_crosswalk",
    "min_coverage_ratio": DEFAULT_COVERAGE_MIN_RATIO,
}

def eval_handoff_coverage_issues(
    payload: dict[str, Any],
    *,
    workspace_dir: Path | None,
) -> list[str]:
    """Coverage contract check for eval handoff payloads."""
    return check_coverage_contract(
        workspace_dir=workspace_dir or Path("."),
        coverage_contract=EVAL_COVERAGE_CONTRACT,
        artifact=payload,
    )


def _row_has_chunk_ids(row: dict[str, Any]) -> bool:
    chunk_ids = row.get("source_chunk_ids") or []
    return isinstance(chunk_ids, list) and any(str(item).strip() for item in chunk_ids)


def _eval_substance_issues(
    payload: dict[str, Any],
    *,
    workspace_dir: Path | None,
) -> list[str]:
    issues: list[str] = []
    crosswalk = payload.get("eval_crosswalk")
    if not isinstance(crosswalk, list):
        issues.append("eval_crosswalk must be an array")
        return issues
    if not crosswalk:
        issues.append(
            "eval_crosswalk is empty — add substantive rows or document gaps in claim_gaps[]"
        )
        return issues

    issues.extend(substance_issues_for_crosswalk(crosswalk, workspace_dir=workspace_dir))
    if workspace_dir is not None:
        issues.extend(eval_handoff_coverage_issues(payload, workspace_dir=workspace_dir))

    material = [
        row
        for row in crosswalk
        if isinstance(row, dict) and str(row.get("evaluation_factor") or "").strip()
    ]
    cited = [row for row in material if _row_has_chunk_ids(row)]
    if len(material) >= 3 and len(cited) < max(2, int(len(material) * 0.75)):
        issues.append(
            "eval_crosswalk rows lack source_chunk_ids — "
            "ground each row in scratchpad chunk IDs before chain continues"
        )
    return issues


def _workload_substance_issues(
    payload: dict[str, Any],
    *,
    workspace_dir: Path | None = None,
) -> list[str]:
    del workspace_dir
    frame = payload.get("mission_readiness_frame")
    if not isinstance(frame, dict):
        frame = {}
    outcome = str(
        frame.get("readiness_outcome") or payload.get("readiness_outcome") or ""
    ).strip()
    enablers = frame.get("workload_enablers") or payload.get("workload_enablers") or []
    if not outcome and not (isinstance(enablers, list) and enablers):
        return [
            "workload_handoff.json: readiness_outcome and workload_enablers both empty"
        ]
    return []


def _pains_substance_issues(
    payload: dict[str, Any],
    *,
    workspace_dir: Path | None = None,
) -> list[str]:
    del workspace_dir
    pains = payload.get("customer_pain_points") or []
    if not isinstance(pains, list) or not pains:
        return [
            "pains_handoff.json: customer_pain_points empty — "
            "retrieve program-office pains or claim_gaps[]"
        ]
    cited = [row for row in pains if isinstance(row, dict) and _row_has_chunk_ids(row)]
    if not cited:
        return ["pains_handoff.json: no customer_pain_points carry source_chunk_ids"]
    return []


def _modernization_substance_issues(
    payload: dict[str, Any],
    *,
    workspace_dir: Path | None = None,
) -> list[str]:
    del workspace_dir
    methods = payload.get("current_methods") or []
    innovations = payload.get("innovation_opportunities") or []
    if not (isinstance(methods, list) and methods) and not (
        isinstance(innovations, list) and innovations
    ):
        return [
            "modernization_handoff.json: current_methods and "
            "innovation_opportunities both empty"
        ]
    return []


def _tea_leaves_substance_issues(
    payload: dict[str, Any],
    *,
    workspace_dir: Path | None = None,
) -> list[str]:
    del workspace_dir
    normalized = TeaLeavesHandoff.from_payload(payload).model_dump()
    signals = normalized.get("importance_signals") or []
    implicit = normalized.get("implicit_criteria") or []
    if not (isinstance(signals, list) and signals) and not (
        isinstance(implicit, list) and implicit
    ):
        return [
            "tea_leaves_handoff.json: importance_signals and implicit_criteria both empty"
        ]
    return []


def _win_themes_substance_issues(
    payload: dict[str, Any],
    *,
    workspace_dir: Path | None = None,
) -> list[str]:
    del workspace_dir
    themes = payload.get("win_theme_candidates") or []
    if not isinstance(themes, list) or not themes:
        return ["win_themes_handoff.json: win_theme_candidates empty"]
    return []


def _capability_overlay_substance_issues(
    payload: dict[str, Any],
    *,
    workspace_dir: Path | None = None,
) -> list[str]:
    del workspace_dir
    overlay = payload.get("capability_overlay")
    if not isinstance(overlay, dict):
        return ["capability_overlay_handoff.json: capability_overlay missing or not an object"]
    issues: list[str] = []
    if not str(overlay.get("vendor") or "").strip():
        issues.append("capability_overlay.vendor is empty")
    capabilities = overlay.get("platform_capabilities") or []
    mappings = overlay.get("pain_point_mappings") or overlay.get("mappings") or []
    innovations = overlay.get("innovation_links") or []
    if not isinstance(capabilities, list) or not capabilities:
        issues.append("capability_overlay.platform_capabilities is missing or empty")
    if not isinstance(mappings, list) or not mappings:
        issues.append("capability_overlay.pain_point_mappings is missing or empty")
    if not isinstance(innovations, list) or not innovations:
        issues.append("capability_overlay.innovation_links is missing or empty")
    return issues


def handoff_substance_issues(
    handoff_name: str,
    payload: dict[str, Any],
    *,
    workspace_dir: Path | None,
) -> list[str]:
    """Return substance issues for one handoff JSON payload."""
    if handoff_name == "eval_handoff.json":
        return _eval_substance_issues(payload, workspace_dir=workspace_dir)
    if handoff_name == "workload_handoff.json":
        return _workload_substance_issues(payload, workspace_dir=workspace_dir)
    if handoff_name == "pains_handoff.json":
        return _pains_substance_issues(payload, workspace_dir=workspace_dir)
    if handoff_name == "modernization_handoff.json":
        return _modernization_substance_issues(payload, workspace_dir=workspace_dir)
    if handoff_name == "tea_leaves_handoff.json":
        return _tea_leaves_substance_issues(payload, workspace_dir=workspace_dir)
    if handoff_name == "win_themes_handoff.json":
        return _win_themes_substance_issues(payload, workspace_dir=workspace_dir)
    if handoff_name == "capability_overlay_handoff.json":
        return _capability_overlay_substance_issues(payload, workspace_dir=workspace_dir)
    return []


def validate_handoff_artifact_substance(
    handoff_name: str,
    path: Path,
    *,
    workspace_dir: Path | None,
) -> list[str]:
    """Schema + substance checks for one handoff file."""
    issues: list[str] = []
    if not path.is_file():
        return [f"{handoff_name} missing at {path}"]

    try:
        validate_handoff_file(path)
    except Exception as exc:  # noqa: BLE001
        return [f"{handoff_name} contract: {exc}"]

    try:
        payload = load_handoff_dict(path)
    except (OSError, ValueError):
        return [f"{handoff_name} is unreadable or not a JSON object"]
    if not isinstance(payload, dict):
        return [f"{handoff_name} is unreadable or not a JSON object"]

    issues.extend(
        handoff_substance_issues(handoff_name, payload, workspace_dir=workspace_dir)
    )
    return issues


def validate_handoff_run(
    run_dir: Path,
    *,
    deliverable: str,
    workspace_dir: Path | None = None,
) -> list[str]:
    """Validate one micro-skill run directory against its handoff deliverable."""
    handoff_path = Path(run_dir) / "artifacts" / deliverable
    resolved_workspace = workspace_dir or resolve_workspace_dir_from_run_dir(Path(run_dir))
    return validate_handoff_artifact_substance(
        deliverable,
        handoff_path,
        workspace_dir=resolved_workspace,
    )


def handoff_continue_message(
    run_dir: Path,
    *,
    deliverable: str,
    label: str,
) -> str | None:
    """Generic depth-gate nudge for micro-skill handoffs."""
    issues = validate_handoff_run(run_dir, deliverable=deliverable)
    if not issues:
        return None
    joined = "; ".join(issues[:8])
    if len(issues) > 8:
        joined += f"; …and {len(issues) - 8} more"
    return (
        f"{label} incomplete — do NOT finalize. "
        f"{joined}. "
        "Continue retrieval and expand the handoff or log honest claim_gaps[]."
    )