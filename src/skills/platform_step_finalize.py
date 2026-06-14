"""Platform finalize node for every mission-readiness chain step."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.skills.handoff_quality import (
    _SKILL_EXPECTED_HANDOFF,
    validate_handoff_artifact,
)
from src.skills.platform_eval_finalize import finalize_eval_handoff, split_eval_gate_issues
from src.skills.readiness_content_gates import compiler_output_substance_issues
from src.skills.source_citations import resolve_workspace_dir_from_run_dir

logger = logging.getLogger(__name__)

_RETRIABLE_MARKERS = (
    "coverage:",
    "undefined acronyms",
    "eval_crosswalk row",
    "near-duplicate",
    "crosswalk rows lack",
    "invented factor",
    "ungrounded row",
    "source_chunk_ids",
    "both empty",
    "empty —",
    "lack source",
    "substance",
    "compressed",
    "brief.md:",
    "section",
)


def split_platform_gate_issues(issues: list[str]) -> tuple[list[str], list[str]]:
    """Partition gate issues into hard-blocking vs retrieve-retry."""
    blocking: list[str] = []
    retriable: list[str] = []
    for issue in issues:
        lowered = str(issue or "").strip().lower()
        if any(marker in lowered for marker in _RETRIABLE_MARKERS):
            retriable.append(str(issue).strip())
        elif lowered:
            blocking.append(str(issue).strip())
    return blocking, retriable


def _gate_result(
    *,
    issues: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    blocking, retriable = split_platform_gate_issues(issues)
    return {
        "issues": issues,
        "blocking_issues": blocking,
        "retriable_issues": retriable,
        "warnings": warnings,
        "passed": not issues,
    }


def _validate_compiler_run(run_dir: Path) -> list[str]:
    issues = list(compiler_output_substance_issues(run_dir))
    from src.skills.skill_local_tools import load_skill_tool_module

    skill_dir = Path(__file__).resolve().parents[2] / ".github" / "skills" / "mission-readiness-framer"
    module = load_skill_tool_module(skill_dir, "mission_readiness_tools")
    try:
        issues.extend(module.validate_skill_run(run_dir, user_prompt=""))
    except TypeError:
        issues.extend(module.validate_skill_run(run_dir))
    return issues


async def finalize_step_handoff(
    *,
    skill: str,
    run_dir: Path,
    workspace_dir: Path,
    loop_response: str = "",
) -> dict[str, Any]:
    """Platform pipeline finalize: skill-specific expand/validate, no main-model turns."""
    skill_name = str(skill or "").strip().lower()

    if skill_name == "readiness-frame-eval":
        return await finalize_eval_handoff(
            run_dir=run_dir,
            workspace_dir=workspace_dir,
            loop_response=loop_response,
        )

    if skill_name == "mission-readiness-framer":
        return _gate_result(issues=_validate_compiler_run(run_dir), warnings=[])

    handoff_name = _SKILL_EXPECTED_HANDOFF.get(skill_name)
    if not handoff_name:
        return _gate_result(issues=[], warnings=[])

    resolved_workspace = resolve_workspace_dir_from_run_dir(run_dir) or workspace_dir
    path = run_dir / "artifacts" / handoff_name
    issues = validate_handoff_artifact(
        handoff_name,
        path,
        workspace_dir=resolved_workspace,
    )
    prefixed = [f"handoff_quality: {issue}" for issue in issues]
    return _gate_result(issues=prefixed, warnings=[])