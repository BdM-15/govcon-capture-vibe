"""Shared substance gates for readiness-frame micro-skill handoffs."""

from __future__ import annotations

import re
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
    normalize_pains_payload,
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
    if workspace_dir is not None:
        from src.skills.evidence_gates import undocumented_material_factor_labels

        gaps = payload.get("claim_gaps") or []
        undocumented = undocumented_material_factor_labels(
            workspace_dir=workspace_dir,
            crosswalk=crosswalk if isinstance(crosswalk, list) else [],
            claim_gaps=gaps if isinstance(gaps, list) else [],
        )
        if undocumented:
            sample = ", ".join(undocumented[:5])
            suffix = "…" if len(undocumented) > 5 else ""
            issues.append(
                "eval_handoff.json: claim_gaps[] missing verbatim material factor names "
                f"({sample}{suffix}) — use inventory labels from eval_batch_manifest"
            )
    return issues


def _workload_row_has_citation(row: Any) -> bool:
    if isinstance(row, dict):
        return _row_has_chunk_ids(row)
    text = str(row or "").strip()
    if not text:
        return False
    return bool(
        re.search(r"(?:doc-|chunk-|tb-)[a-zA-Z0-9_-]+", text, re.IGNORECASE)
    )


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
    failures = (
        frame.get("failure_modes_feared") or payload.get("failure_modes_feared") or []
    )
    issues: list[str] = []
    if not outcome and not (isinstance(enablers, list) and enablers):
        issues.append(
            "workload_handoff.json: readiness_outcome and workload_enablers both empty"
        )
        return issues
    if len(outcome) < 80:
        issues.append(
            "workload_handoff.json: readiness_outcome too thin — "
            "need 2–4 sentences of program-office readiness outcome"
        )
    if not isinstance(enablers, list) or len(enablers) < 3:
        issues.append(
            "workload_handoff.json: workload_enablers needs >= 3 cited PWS/QASP/CDRL/transition rows"
        )
    else:
        uncited = [
            index
            for index, row in enumerate(enablers, start=1)
            if not _workload_row_has_citation(row)
        ]
        if uncited:
            issues.append(
                "workload_handoff.json: workload_enablers rows "
                f"{uncited[:4]} lack source_chunk_ids"
            )
        string_rows = [index for index, row in enumerate(enablers, start=1) if isinstance(row, str)]
        if string_rows:
            issues.append(
                "workload_handoff.json: workload_enablers must be objects "
                "(enabler, readiness_link, source_chunk_ids) — not plain strings"
            )
    if not isinstance(failures, list) or len(failures) < 3:
        issues.append(
            "workload_handoff.json: failure_modes_feared needs >= 3 cited degradation paths"
        )
    else:
        uncited_failures = [
            index
            for index, row in enumerate(failures, start=1)
            if not _workload_row_has_citation(row)
        ]
        if uncited_failures:
            issues.append(
                "workload_handoff.json: failure_modes_feared rows "
                f"{uncited_failures[:4]} lack source_chunk_ids"
            )
        string_failures = [
            index for index, row in enumerate(failures, start=1) if isinstance(row, str)
        ]
        if string_failures:
            issues.append(
                "workload_handoff.json: failure_modes_feared must be objects "
                "(failure_mode, customer_impact, source_chunk_ids) — not plain strings"
            )
    return issues


def _pains_row_has_citation(row: Any) -> bool:
    return isinstance(row, dict) and _row_has_chunk_ids(row)


def _pains_row_has_substance(row: dict[str, Any]) -> bool:
    challenge = str(row.get("challenge_type") or "").strip()
    rationale = str(row.get("rationale") or "").strip()
    readiness = str(row.get("readiness_link") or "").strip()
    return (
        len(challenge) >= 12
        and len(rationale) >= 70
        and len(readiness) >= 50
        and _pains_row_has_citation(row)
    )


def _pains_substance_issues(
    payload: dict[str, Any],
    *,
    workspace_dir: Path | None = None,
) -> list[str]:
    del workspace_dir
    raw_pains = payload.get("customer_pain_points") or []
    payload = normalize_pains_payload(payload)
    pains = payload.get("customer_pain_points") or []
    issues: list[str] = []
    if not isinstance(pains, list) or not pains:
        return [
            "pains_handoff.json: customer_pain_points empty — "
            "retrieve program-office pains or claim_gaps[]"
        ]
    if len(pains) < 3:
        issues.append(
            "pains_handoff.json: customer_pain_points needs >= 3 cited "
            "program-office pain rows when evidence supports"
        )
    string_rows = [
        index for index, row in enumerate(raw_pains, start=1) if isinstance(row, str)
    ]
    if string_rows:
        issues.append(
            "pains_handoff.json: customer_pain_points must be objects "
            "(visibility, challenge_type, rationale, readiness_link, source_chunk_ids) "
            "— not plain strings"
        )
    uncited = [
        index
        for index, row in enumerate(pains, start=1)
        if isinstance(row, dict) and not _pains_row_has_citation(row)
    ]
    if uncited:
        issues.append(
            "pains_handoff.json: customer_pain_points rows "
            f"{uncited[:4]} lack source_chunk_ids"
        )
    thin = [
        index
        for index, row in enumerate(pains, start=1)
        if isinstance(row, dict) and not _pains_row_has_substance(row)
    ]
    if thin and len(pains) >= 3:
        issues.append(
            "pains_handoff.json: customer_pain_points rows "
            f"{thin[:4]} too thin — need challenge_type, rationale (>=70 chars), "
            "readiness_link (>=50 chars), and source_chunk_ids"
        )
    visibilities = {
        str(row.get("visibility") or "").strip().lower()
        for row in pains
        if isinstance(row, dict)
    }
    if len(pains) >= 3 and not (
        "explicit" in visibilities and ({"latent", "structural"} & visibilities)
    ):
        issues.append(
            "pains_handoff.json: mix explicit with latent or structural pains "
            "when scratchpad evidence supports Shipley visibility types"
        )
    return issues


def _modernization_method_has_substance(row: dict[str, Any]) -> bool:
    method = str(row.get("method") or "").strip()
    implied_by = str(row.get("implied_by") or "").strip()
    return len(method) >= 12 and len(implied_by) >= 50 and _row_has_chunk_ids(row)


def _modernization_innovation_has_substance(row: dict[str, Any]) -> bool:
    opportunity = str(row.get("opportunity") or "").strip()
    value = str(row.get("value") or "").strip()
    return len(opportunity) >= 12 and len(value) >= 50 and _row_has_chunk_ids(row)


def _modernization_substance_issues(
    payload: dict[str, Any],
    *,
    workspace_dir: Path | None = None,
) -> list[str]:
    del workspace_dir
    from src.skills.readiness_handoff_models import normalize_modernization_payload

    raw_methods = payload.get("current_methods") or []
    raw_innovations = payload.get("innovation_opportunities") or []
    payload = normalize_modernization_payload(payload)
    methods = payload.get("current_methods") or []
    innovations = payload.get("innovation_opportunities") or []
    issues: list[str] = []
    if not (isinstance(methods, list) and methods) and not (
        isinstance(innovations, list) and innovations
    ):
        return [
            "modernization_handoff.json: current_methods and "
            "innovation_opportunities both empty — retrieve PWS methods or claim_gaps[]"
        ]
    if not isinstance(methods, list) or len(methods) < 3:
        issues.append(
            "modernization_handoff.json: current_methods needs >= 3 cited "
            "PWS/QASP-implied incumbent rows"
        )
    if not isinstance(innovations, list) or len(innovations) < 2:
        issues.append(
            "modernization_handoff.json: innovation_opportunities needs >= 2 cited "
            "customer-grounded improvement rows"
        )
    method_strings = [
        index for index, row in enumerate(raw_methods, start=1) if isinstance(row, str)
    ]
    if method_strings:
        issues.append(
            "modernization_handoff.json: current_methods must be objects "
            "(method, implied_by, tooling, fit_to_scope, source_chunk_ids) — not plain strings"
        )
    innovation_strings = [
        index
        for index, row in enumerate(raw_innovations, start=1)
        if isinstance(row, str)
    ]
    if innovation_strings:
        issues.append(
            "modernization_handoff.json: innovation_opportunities must be objects "
            "(opportunity, value, customer_grounded, fit_to_scope, source_chunk_ids) "
            "— not plain strings"
        )
    uncited_methods = [
        index
        for index, row in enumerate(methods, start=1)
        if isinstance(row, dict) and not _row_has_chunk_ids(row)
    ]
    if uncited_methods:
        issues.append(
            "modernization_handoff.json: current_methods rows "
            f"{uncited_methods[:4]} lack source_chunk_ids"
        )
    uncited_innovations = [
        index
        for index, row in enumerate(innovations, start=1)
        if isinstance(row, dict) and not _row_has_chunk_ids(row)
    ]
    if uncited_innovations:
        issues.append(
            "modernization_handoff.json: innovation_opportunities rows "
            f"{uncited_innovations[:4]} lack source_chunk_ids"
        )
    thin_methods = [
        index
        for index, row in enumerate(methods, start=1)
        if isinstance(row, dict) and not _modernization_method_has_substance(row)
    ]
    if thin_methods and len(methods) >= 3:
        issues.append(
            "modernization_handoff.json: current_methods rows "
            f"{thin_methods[:4]} too thin — need method, implied_by (>=50 chars), "
            "and source_chunk_ids"
        )
    thin_innovations = [
        index
        for index, row in enumerate(innovations, start=1)
        if isinstance(row, dict) and not _modernization_innovation_has_substance(row)
    ]
    if thin_innovations and len(innovations) >= 2:
        issues.append(
            "modernization_handoff.json: innovation_opportunities rows "
            f"{thin_innovations[:4]} too thin — need opportunity, value (>=50 chars), "
            "and source_chunk_ids"
        )
    return issues


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