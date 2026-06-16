"""Platform hooks for readiness-frame-modernization deliverable quality."""

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

_DELIVERABLE = "modernization_handoff.json"
_LABEL = "Modernization handoff"


def validate_skill_run(
    run_dir: Path,
    *,
    user_prompt: str = "",
) -> list[str]:
    del user_prompt
    if validate_handoff_run is None:
        return []
    try:
        from src.skills.modernization_handoff_repair import repair_modernization_handoff

        repair_modernization_handoff(run_dir)
    except ImportError:
        pass
    return validate_handoff_run(run_dir, deliverable=_DELIVERABLE)


def artifact_continue_message(run_dir: Path) -> str | None:
    if handoff_continue_message is None:
        return None
    return handoff_continue_message(
        run_dir,
        deliverable=_DELIVERABLE,
        label=_LABEL,
    )