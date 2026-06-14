"""Shared chain-step quality enforcement for SkillChainExecutor and LangGraph runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.skills.handoff_quality import step_quality_errors


def apply_step_quality_gate(
    step_run: Any,
    *,
    finish_reason: str,
    warnings: list[str] | None,
    workspace_root: Path,
) -> bool:
    """
    Fail the step when handoff or depth quality breaches hard gates.

    Returns True when the step was marked failed.
    """
    errors = step_quality_errors(
        finish_reason=finish_reason,
        warnings=warnings,
        step_run=step_run,
        workspace_root=workspace_root,
    )
    if not errors:
        return False
    step_run.status = "failed"
    step_run.error = "; ".join(errors[:6])
    if len(errors) > 6:
        step_run.error += f"; …and {len(errors) - 6} more"
    return True