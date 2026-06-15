"""Platform finalize node for every mission-readiness chain step."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.skills.handoff_quality import _SKILL_EXPECTED_HANDOFF
from src.skills.platform_eval_finalize import finalize_eval_handoff, split_eval_gate_issues
from src.skills.readiness_content_gates import (
    apply_known_acronym_expansions,
    apply_known_acronym_expansions_to_frame_payload,
    compiler_output_substance_issues,
    frame_narrative_text_for_acronym_gate,
    undefined_acronyms,
)
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


def repair_compiler_artifacts(run_dir: Path) -> bool:
    """Pre-gate repair: seed verbatim bank from citations + expand known acronyms."""
    from src.skills.mission_readiness_merge import (
        is_compiler_run_dir,
        refresh_compiler_verbatim_section,
        seed_verbatim_extracts_from_citations,
    )

    if not is_compiler_run_dir(run_dir):
        return False

    artifacts = run_dir / "artifacts"
    frame_path = artifacts / "mission_readiness_frame.json"
    brief_path = artifacts / "brief.md"
    changed = False
    payload: dict[str, Any] | None = None

    if frame_path.is_file():
        try:
            loaded = json.loads(frame_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, dict):
            before = json.dumps(loaded, sort_keys=True, ensure_ascii=False)
            payload = seed_verbatim_extracts_from_citations(loaded)
            payload = apply_known_acronym_expansions_to_frame_payload(payload)
            after = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            if after != before:
                frame_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                changed = True
                refresh_compiler_verbatim_section(run_dir, payload=payload)

    if brief_path.is_file():
        try:
            brief = brief_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return changed
        from src.skills.readiness_content_gates import _brief_text_for_acronym_gate

        combined = _brief_text_for_acronym_gate(brief)
        if isinstance(payload, dict):
            combined = (
                f"{_brief_text_for_acronym_gate(brief)}\n"
                f"{frame_narrative_text_for_acronym_gate(payload)}"
            )
        targets = undefined_acronyms(combined)
        revised = apply_known_acronym_expansions(brief, targets=targets)
        if revised.strip() and revised != brief:
            brief_path.write_text(revised, encoding="utf-8")
            changed = True

    return changed


def _skill_dir_for_name(skill_name: str) -> Path:
    return Path(__file__).resolve().parents[2] / ".github" / "skills" / skill_name


def _validate_micro_skill_run(skill_name: str, run_dir: Path) -> list[str]:
    """Gate micro-skill handoff via skill-declared validate_skill_run hook."""
    from src.skills.skill_local_tools import resolve_skill_run_validator

    skill_dir = _skill_dir_for_name(skill_name)
    validate_run = resolve_skill_run_validator(skill_dir)
    if validate_run is None:
        return [f"handoff_quality: {skill_name} missing validate_skill_run hook"]
    try:
        return list(validate_run(run_dir, user_prompt=""))
    except TypeError:
        return list(validate_run(run_dir))


def _validate_compiler_run(run_dir: Path) -> list[str]:
    from src.skills.mission_readiness_merge import write_compiler_brief_scaffold

    write_compiler_brief_scaffold(run_dir)
    repair_compiler_artifacts(run_dir)
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

    if skill_name not in _SKILL_EXPECTED_HANDOFF:
        return _gate_result(issues=[], warnings=[])

    issues = _validate_micro_skill_run(skill_name, run_dir)
    prefixed = [
        issue if str(issue).startswith("handoff_quality:") else f"handoff_quality: {issue}"
        for issue in issues
    ]
    return _gate_result(issues=prefixed, warnings=[])