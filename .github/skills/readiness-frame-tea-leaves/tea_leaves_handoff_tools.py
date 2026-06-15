"""Platform hooks for readiness-frame-tea-leaves deliverable quality."""

from __future__ import annotations

from pathlib import Path

try:
    from src.skills.readiness_handoff_gates import (
        handoff_continue_message,
        validate_handoff_run,
    )
except ImportError:
    handoff_continue_message = None  # type: ignore[assignment,misc]
    validate_handoff_run = None  # type: ignore[assignment,misc]

_DELIVERABLE = "tea_leaves_handoff.json"
_LABEL = "Tea-leaves handoff"


def validate_skill_run(
    run_dir: Path,
    *,
    user_prompt: str = "",
) -> list[str]:
    del user_prompt
    if validate_handoff_run is None:
        return []
    return validate_handoff_run(run_dir, deliverable=_DELIVERABLE)


def artifact_continue_message(run_dir: Path) -> str | None:
    if handoff_continue_message is None:
        return None
    return handoff_continue_message(
        run_dir,
        deliverable=_DELIVERABLE,
        label=_LABEL,
    )