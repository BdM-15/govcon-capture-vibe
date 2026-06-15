"""Runtime quality gates for readiness-frame chain handoffs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.skills.evidence_gates import (
    DEFAULT_COVERAGE_MIN_RATIO,
    check_coverage_contract,
    crosswalk_material_row_labels,
    minimum_required_crosswalk_rows,
)
from src.skills.readiness_content_gates import (
    compiler_output_substance_issues,
    substance_issues_for_crosswalk,
)
from src.skills.readiness_handoff_models import (
    TeaLeavesHandoff,
    load_handoff_dict,
    validate_handoff_file,
)
from src.skills.source_citations import resolve_workspace_dir_from_run_dir

_SKILL_EXPECTED_HANDOFF: dict[str, str] = {
    "readiness-frame-eval": "eval_handoff.json",
    "readiness-frame-workload": "workload_handoff.json",
    "readiness-frame-pains": "pains_handoff.json",
    "readiness-frame-modernization": "modernization_handoff.json",
    "readiness-frame-tea-leaves": "tea_leaves_handoff.json",
    "readiness-frame-win-themes": "win_themes_handoff.json",
    "readiness-frame-external-research": "capability_overlay_handoff.json",
}

_HANDOFF_FILENAMES = frozenset(
    {
        "eval_handoff.json",
        "workload_handoff.json",
        "pains_handoff.json",
        "modernization_handoff.json",
        "tea_leaves_handoff.json",
        "win_themes_handoff.json",
        "capability_overlay_handoff.json",
    }
)

_EVAL_COVERAGE_CONTRACT = {
    "artifact_path": "eval_handoff.json",
    "required_entity_types": ["evaluation_factor", "subfactor"],
    "rule": "one_row_per_entity",
    "rows_key": "eval_crosswalk",
    "min_coverage_ratio": DEFAULT_COVERAGE_MIN_RATIO,
}

_BLOCKING_FINISH_REASONS = frozenset({"depth_incomplete", "error"})

def _is_compiler_step(step_run: Any) -> bool:
    skill = str(getattr(step_run, "skill", "") or "").strip().lower()
    if skill != "mission-readiness-framer":
        return False
    run_dir = str(getattr(step_run, "run_dir", "") or "").strip()
    if not run_dir:
        return False
    from src.skills.mission_readiness_merge import is_compiler_run_dir

    return is_compiler_run_dir(Path(run_dir))


def _compiler_substance_errors(step_run: Any) -> list[str]:
    run_dir = str(getattr(step_run, "run_dir", "") or "").strip()
    if not run_dir:
        return []
    path = Path(run_dir)
    from src.skills.platform_step_finalize import repair_compiler_artifacts

    repair_compiler_artifacts(path)
    return compiler_output_substance_issues(path)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return load_handoff_dict(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _row_has_chunk_ids(row: dict[str, Any]) -> bool:
    chunk_ids = row.get("source_chunk_ids") or []
    return isinstance(chunk_ids, list) and any(str(item).strip() for item in chunk_ids)


def validate_handoff_artifact(
    handoff_name: str,
    path: Path,
    *,
    workspace_dir: Path | None,
) -> list[str]:
    """Deterministic substance checks for one handoff JSON artifact."""
    issues: list[str] = []
    if not path.is_file():
        return [f"{handoff_name} missing at {path}"]

    try:
        validate_handoff_file(path)
    except Exception as exc:  # noqa: BLE001
        issues.append(f"{handoff_name} contract: {exc}")
        return issues

    payload = _load_json(path)
    if payload is None:
        return [f"{handoff_name} is unreadable or not a JSON object"]

    if handoff_name == "eval_handoff.json":
        crosswalk = payload.get("eval_crosswalk")
        if not isinstance(crosswalk, list) or not crosswalk:
            issues.append(
                "eval_handoff.json: eval_crosswalk is empty — add substantive rows or claim_gaps[]"
            )
        elif workspace_dir is not None:
            issues.extend(
                check_coverage_contract(
                    workspace_dir=workspace_dir,
                    coverage_contract=_EVAL_COVERAGE_CONTRACT,
                    artifact=payload,
                )
            )
        if isinstance(crosswalk, list) and crosswalk:
            issues.extend(
                substance_issues_for_crosswalk(crosswalk, workspace_dir=workspace_dir)
            )
            material = [
                row
                for row in crosswalk
                if isinstance(row, dict) and str(row.get("evaluation_factor") or "").strip()
            ]
            cited = [row for row in material if _row_has_chunk_ids(row)]
            if len(material) >= 3 and len(cited) < max(2, int(len(material) * 0.75)):
                issues.append(
                    "eval_handoff.json: crosswalk rows lack source_chunk_ids — "
                    "ground each row in scratchpad chunk IDs before chain continues"
                )
        return issues

    if handoff_name == "workload_handoff.json":
        frame = payload.get("mission_readiness_frame")
        if not isinstance(frame, dict):
            frame = {}
        outcome = str(
            frame.get("readiness_outcome") or payload.get("readiness_outcome") or ""
        ).strip()
        enablers = frame.get("workload_enablers") or payload.get("workload_enablers") or []
        if not outcome and not (isinstance(enablers, list) and enablers):
            issues.append(
                "workload_handoff.json: readiness_outcome and workload_enablers both empty"
            )
        return issues

    if handoff_name == "pains_handoff.json":
        pains = payload.get("customer_pain_points") or []
        if not isinstance(pains, list) or not pains:
            issues.append(
                "pains_handoff.json: customer_pain_points empty — retrieve program-office pains or claim_gaps[]"
            )
        else:
            cited = [
                row
                for row in pains
                if isinstance(row, dict) and _row_has_chunk_ids(row)
            ]
            if not cited:
                issues.append(
                    "pains_handoff.json: no customer_pain_points carry source_chunk_ids"
                )
        return issues

    if handoff_name == "modernization_handoff.json":
        methods = payload.get("current_methods") or []
        innovations = payload.get("innovation_opportunities") or []
        if not (isinstance(methods, list) and methods) and not (
            isinstance(innovations, list) and innovations
        ):
            issues.append(
                "modernization_handoff.json: current_methods and innovation_opportunities both empty"
            )
        return issues

    if handoff_name == "tea_leaves_handoff.json":
        normalized = TeaLeavesHandoff.from_payload(payload).model_dump()
        signals = normalized.get("importance_signals") or []
        implicit = normalized.get("implicit_criteria") or []
        if not (isinstance(signals, list) and signals) and not (
            isinstance(implicit, list) and implicit
        ):
            issues.append(
                "tea_leaves_handoff.json: importance_signals and implicit_criteria both empty"
            )
        return issues

    if handoff_name == "win_themes_handoff.json":
        themes = payload.get("win_theme_candidates") or []
        if not isinstance(themes, list) or not themes:
            issues.append("win_themes_handoff.json: win_theme_candidates empty")
        return issues

    return issues


def _skill_dir_for_name(skill_name: str) -> Path:
    return Path(__file__).resolve().parents[2] / ".github" / "skills" / skill_name


def _validate_via_skill_run_hook(
    skill_name: str,
    run_dir: Path,
) -> list[str] | None:
    """Use skill-declared validate_skill_run when present (solo + chain share one gate)."""
    from src.skills.skill_local_tools import resolve_skill_run_validator

    skill_dir = _skill_dir_for_name(skill_name)
    if not skill_dir.is_dir():
        return None
    validate_run = resolve_skill_run_validator(skill_dir)
    if validate_run is None:
        return None
    try:
        issues = list(validate_run(run_dir, user_prompt=""))
    except TypeError:
        issues = list(validate_run(run_dir))
    return [f"handoff_quality: {issue}" for issue in issues if str(issue or "").strip()]


def validate_step_handoffs(step_run: Any, workspace_root: Path) -> list[str]:
    """Return blocking errors for readiness-frame handoff artifacts from one chain step."""
    errors: list[str] = []
    run_dir = str(getattr(step_run, "run_dir", "") or "").strip()
    if not run_dir:
        return errors

    workspace_dir = resolve_workspace_dir_from_run_dir(Path(run_dir)) or Path(workspace_root)
    artifacts_dir = Path(run_dir) / "artifacts"
    skill_name = str(getattr(step_run, "skill", "") or "").strip().lower()
    run_path = Path(run_dir)

    hook_errors = _validate_via_skill_run_hook(skill_name, run_path)
    if hook_errors is not None:
        return hook_errors

    expected = _SKILL_EXPECTED_HANDOFF.get(skill_name)
    if expected:
        path = artifacts_dir / expected
        for issue in validate_handoff_artifact(expected, path, workspace_dir=workspace_dir):
            errors.append(f"handoff_quality: {issue}")
        return errors

    if not artifacts_dir.is_dir():
        return errors

    seen: set[str] = set()
    for artifact in getattr(step_run, "artifacts", None) or []:
        name = str(artifact.get("name") or "").strip().lower()
        if name not in _HANDOFF_FILENAMES or name in seen:
            continue
        seen.add(name)
        path = artifacts_dir / name
        for issue in validate_handoff_artifact(name, path, workspace_dir=workspace_dir):
            errors.append(f"handoff_quality: {issue}")

    return errors


def step_quality_errors(
    *,
    finish_reason: str,
    warnings: list[str] | None,
    step_run: Any,
    workspace_root: Path,
) -> list[str]:
    """Collect blocking quality failures for a finished chain step."""
    errors: list[str] = []
    handoff_errors = validate_step_handoffs(step_run, workspace_root)
    compiler_step = _is_compiler_step(step_run)
    compiler_errors = _compiler_substance_errors(step_run) if compiler_step else []
    reason = str(finish_reason or "").strip().lower()
    if reason in _BLOCKING_FINISH_REASONS:
        if reason == "error":
            errors.append(f"skill run finish_reason={reason}")
        elif reason == "depth_incomplete" and (
            handoff_errors or compiler_step or compiler_errors
        ):
            errors.append(f"skill run finish_reason={reason}")

    for warning in warnings or []:
        text = str(warning or "").strip()
        if text.startswith("depth_audit: coverage:"):
            errors.append(text.removeprefix("depth_audit: "))
        elif text.startswith("audit: coverage:"):
            errors.append(text.removeprefix("audit: "))
        elif compiler_step and text.startswith("depth_audit:"):
            errors.append(text.removeprefix("depth_audit: "))

    errors.extend(compiler_errors)
    errors.extend(handoff_errors)
    return errors


def eval_handoff_coverage_issues(
    payload: dict[str, Any],
    *,
    workspace_dir: Path | None,
) -> list[str]:
    """Coverage contract check for eval handoff payloads."""
    return check_coverage_contract(
        workspace_dir=workspace_dir or Path("."),
        coverage_contract=_EVAL_COVERAGE_CONTRACT,
        artifact=payload,
    )


def material_crosswalk_row_count(crosswalk: list[Any]) -> int:
    return len(crosswalk_material_row_labels(crosswalk))


def required_crosswalk_rows(workspace_dir: Path | None) -> int:
    return minimum_required_crosswalk_rows(workspace_dir)