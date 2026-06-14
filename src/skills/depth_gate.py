"""Platform depth gate — keeps tool loops running until deliverables pass audit."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from src.skills.skill_local_tools import SkillToolsHooks


def _issues_to_continuation(issues: list[str]) -> str:
    joined = "; ".join(issues[:8])
    if len(issues) > 8:
        joined += f"; …and {len(issues) - 8} more"
    return (
        "Depth gate — run is NOT complete. "
        f"{joined}. "
        "Continue: retrieve more package evidence, expand deliverables with "
        "write_file, and do not stop until coverage is complete or gaps are "
        "logged in claim_gaps[]."
    )


def depth_continue_message(
    run_dir: Path,
    *,
    hooks: SkillToolsHooks,
    user_prompt: str = "",
) -> str | None:
    """Return a continuation nudge when skill deliverables fail depth audit."""
    if hooks.artifact_continue is not None:
        message = hooks.artifact_continue(Path(run_dir))
        if message:
            return message
    if hooks.validate_run is not None:
        try:
            issues = hooks.validate_run(Path(run_dir), user_prompt=user_prompt)
        except TypeError:
            issues = hooks.validate_run(Path(run_dir))
        if issues:
            return _issues_to_continuation(issues)
    return None


def make_depth_continue_fn(
    hooks: SkillToolsHooks,
    *,
    user_prompt: str = "",
) -> Optional[Callable[[Path], Optional[str]]]:
    """Build a ``continue_if`` callback when the skill declares depth hooks."""
    if hooks.artifact_continue is None and hooks.validate_run is None:
        return None

    def _continue(run_dir: Path) -> str | None:
        return depth_continue_message(
            run_dir,
            hooks=hooks,
            user_prompt=user_prompt,
        )

    return _continue


def filter_retrieve_only_depth_issues(issues: list[str]) -> list[str]:
    """Drop platform-owned coverage/acronym issues during eval retrieve-only passes."""
    if not issues:
        return []
    from src.skills.platform_eval_finalize import split_eval_gate_issues

    blocking, _ = split_eval_gate_issues(issues)
    return blocking


def depth_gate_issues(
    run_dir: Path,
    *,
    hooks: SkillToolsHooks,
    user_prompt: str = "",
) -> list[str]:
    """Return depth audit issues for a finished or in-progress run."""
    if hooks.validate_run is None:
        return []
    try:
        return list(hooks.validate_run(Path(run_dir), user_prompt=user_prompt))
    except TypeError:
        return list(hooks.validate_run(Path(run_dir)))


def resolve_finish_reason(
    *,
    loop_finish_reason: str,
    depth_issues: list[str],
    hard_cap_hit: bool,
) -> str:
    """Map loop outcome + depth audit to a persisted finish reason."""
    if depth_issues and loop_finish_reason in {"stop", "max_turns", "max_turns_no_summary"}:
        if hard_cap_hit:
            return "depth_incomplete"
        return "depth_incomplete"
    return loop_finish_reason