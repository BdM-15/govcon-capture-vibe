"""Platform hooks for readiness-frame-eval deliverable quality."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from src.skills.handoff_quality import eval_handoff_coverage_issues
    from src.skills.readiness_content_gates import (
        acronym_issues_for_eval_handoff,
        substance_issues_for_crosswalk,
        validate_eval_handoff_write,
    )
    from src.skills.readiness_handoff_models import load_handoff_dict
    from src.skills.source_citations import resolve_workspace_dir_from_run_dir
except ImportError:
    eval_handoff_coverage_issues = None  # type: ignore[assignment,misc]
    validate_eval_handoff_write = None  # type: ignore[assignment,misc]
    substance_issues_for_crosswalk = None  # type: ignore[assignment,misc]
    acronym_issues_for_eval_handoff = None  # type: ignore[assignment,misc]
    load_handoff_dict = None  # type: ignore[assignment,misc]
    resolve_workspace_dir_from_run_dir = None  # type: ignore[assignment,misc]

_DELIVERABLE = "eval_handoff.json"


def validate_write_file(
    run_dir: Path,
    *,
    path: str,
    content: str,
    user_prompt: str = "",
) -> str | None:
    if validate_eval_handoff_write is None:
        return None
    return validate_eval_handoff_write(path=path, content=content)


def validate_skill_run(
    run_dir: Path,
    *,
    user_prompt: str = "",
) -> list[str]:
    del user_prompt
    if substance_issues_for_crosswalk is None:
        return []
    artifacts_dir = Path(run_dir) / "artifacts"
    handoff_path = artifacts_dir / _DELIVERABLE
    if not handoff_path.is_file():
        return [f"missing artifacts/{_DELIVERABLE}"]
    try:
        if load_handoff_dict is not None:
            payload = load_handoff_dict(handoff_path)
        else:
            payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return [f"artifacts/{_DELIVERABLE} is unreadable"]
    if not isinstance(payload, dict):
        return [f"artifacts/{_DELIVERABLE} must be a JSON object"]

    issues: list[str] = []
    crosswalk = payload.get("eval_crosswalk")
    if not isinstance(crosswalk, list):
        issues.append("eval_crosswalk must be an array")
    elif not crosswalk:
        issues.append(
            "eval_crosswalk is empty — add substantive rows or document gaps in claim_gaps[]"
        )
    else:
        issues.extend(substance_issues_for_crosswalk(crosswalk))
        if eval_handoff_coverage_issues is not None and resolve_workspace_dir_from_run_dir is not None:
            workspace_dir = resolve_workspace_dir_from_run_dir(Path(run_dir))
            if workspace_dir is not None:
                issues.extend(
                    eval_handoff_coverage_issues(payload, workspace_dir=workspace_dir)
                )

    if acronym_issues_for_eval_handoff is not None:
        issues.extend(acronym_issues_for_eval_handoff(payload))
    return issues


def artifact_continue_message(run_dir: Path) -> str | None:
    """Depth-gate nudge when eval handoff fails coverage or substance checks."""
    issues = validate_skill_run(run_dir)
    if not issues:
        return None
    joined = "; ".join(issues[:8])
    if len(issues) > 8:
        joined += f"; …and {len(issues) - 8} more"
    return (
        "Eval handoff incomplete — do NOT finalize. "
        f"{joined}. "
        "Continue batched entity-first retrieval: kg_entities for all factors, "
        "kg_chunks per batch of 5–8, expand eval_crosswalk[] or log named claim_gaps[]."
    )