"""Platform hooks for readiness-frame-eval deliverable quality."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from src.skills.readiness_content_gates import (
        acronym_issues_for_text,
        substance_issues_for_crosswalk,
        validate_eval_handoff_write,
    )
except ImportError:
    validate_eval_handoff_write = None  # type: ignore[assignment,misc]
    substance_issues_for_crosswalk = None  # type: ignore[assignment,misc]
    acronym_issues_for_text = None  # type: ignore[assignment,misc]

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
        payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
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

    if acronym_issues_for_text is not None:
        issues.extend(
            acronym_issues_for_text(
                handoff_path.read_text(encoding="utf-8", errors="replace"),
                label=_DELIVERABLE,
            )
        )
    return issues