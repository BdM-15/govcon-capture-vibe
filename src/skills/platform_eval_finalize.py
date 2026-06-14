"""Deterministic eval handoff finalize — expander, admin acronyms, gate (no main-model turns)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PLATFORM_GATE_MARKERS = (
    "coverage:",
    "undefined acronyms",
    "eval_crosswalk row",
    "near-duplicate",
    "crosswalk rows lack",
    "invented factor",
    "ungrounded row",
)


def split_eval_gate_issues(issues: list[str]) -> tuple[list[str], list[str]]:
    """Partition issues into hard-blocking vs retrieve-retry (coverage/substance)."""
    blocking: list[str] = []
    retriable: list[str] = []
    for issue in issues:
        lowered = str(issue or "").strip().lower()
        if any(marker in lowered for marker in _PLATFORM_GATE_MARKERS):
            retriable.append(str(issue).strip())
        elif lowered:
            blocking.append(str(issue).strip())
    return blocking, retriable


def _validate_eval_run(run_dir: Path) -> list[str]:
    from src.skills.skill_local_tools import load_skill_tool_module

    skill_dir = Path(__file__).resolve().parents[2] / ".github" / "skills" / "readiness-frame-eval"
    module = load_skill_tool_module(skill_dir, "eval_handoff_tools")
    return list(module.validate_skill_run(run_dir, user_prompt=""))


async def finalize_eval_handoff(
    *,
    run_dir: Path,
    workspace_dir: Path,
    loop_response: str = "",
) -> dict[str, Any]:
    """
    Platform eval pipeline node: expand crosswalk, admin acronym pass, validate.

    Returns dict with keys: issues, retriable_issues, blocking_issues, warnings, passed.
    """
    warnings: list[str] = []
    from src.skills.eval_handoff_expander import expand_eval_handoff

    try:
        _, expand_warnings = await expand_eval_handoff(
            run_dir=run_dir,
            workspace_dir=workspace_dir,
            loop_response=loop_response,
        )
        warnings.extend(expand_warnings)
    except Exception as exc:  # noqa: BLE001
        logger.warning("eval_finalize expand failed: %s", exc)
        warnings.append(f"eval_finalize: expand_failed: {exc}")

    handoff_path = run_dir / "artifacts" / "eval_handoff.json"
    if handoff_path.is_file():
        try:
            from src.skills.local_llm_admin import (
                admin_model_configured,
                expand_acronyms_in_eval_handoff_json,
            )

            if admin_model_configured():
                original = handoff_path.read_text(encoding="utf-8", errors="replace")
                revised = await expand_acronyms_in_eval_handoff_json(original)
                if revised.strip() and revised != original:
                    handoff_path.write_text(revised, encoding="utf-8")
                    warnings.append("eval_finalize: admin_llm expanded acronyms")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"eval_finalize: admin_acronym_failed: {exc}")

    issues = _validate_eval_run(run_dir)
    blocking, retriable = split_eval_gate_issues(issues)
    passed = not issues
    return {
        "issues": issues,
        "blocking_issues": blocking,
        "retriable_issues": retriable,
        "warnings": warnings,
        "passed": passed,
    }