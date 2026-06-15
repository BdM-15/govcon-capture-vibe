"""Platform hooks for readiness-frame-eval deliverable quality."""

from __future__ import annotations

from pathlib import Path

try:
    from src.skills.readiness_content_gates import validate_eval_handoff_write
    from src.skills.readiness_handoff_gates import validate_handoff_run
except ImportError:
    validate_eval_handoff_write = None  # type: ignore[assignment,misc]
    validate_handoff_run = None  # type: ignore[assignment,misc]

_DELIVERABLE = "eval_handoff.json"


def validate_write_file(
    run_dir: Path,
    *,
    path: str,
    content: str,
    user_prompt: str = "",
) -> str | None:
    del run_dir, user_prompt
    if validate_eval_handoff_write is None:
        return None
    return validate_eval_handoff_write(path=path, content=content)


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