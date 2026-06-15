"""Runtime quality gates for readiness-frame chain handoffs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.skills.readiness_content_gates import compiler_output_substance_issues
from src.skills.readiness_handoff_gates import (
    EVAL_COVERAGE_CONTRACT,
    eval_handoff_coverage_issues,
    validate_handoff_artifact_substance,
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

_HANDOFF_FILENAMES = frozenset(_SKILL_EXPECTED_HANDOFF.values())

_EVAL_COVERAGE_CONTRACT = EVAL_COVERAGE_CONTRACT

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


def validate_handoff_artifact(
    handoff_name: str,
    path: Path,
    *,
    workspace_dir: Path | None,
) -> list[str]:
    """Deterministic substance checks for one handoff JSON artifact."""
    return validate_handoff_artifact_substance(
        handoff_name,
        path,
        workspace_dir=workspace_dir,
    )


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


def material_crosswalk_row_count(crosswalk: list[Any]) -> int:
    from src.skills.evidence_gates import crosswalk_material_row_labels

    return len(crosswalk_material_row_labels(crosswalk))


def required_crosswalk_rows(workspace_dir: Path | None) -> int:
    from src.skills.evidence_gates import minimum_required_crosswalk_rows

    return minimum_required_crosswalk_rows(workspace_dir)