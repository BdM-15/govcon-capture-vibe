"""Deterministic eval handoff finalize — repair, platform expander, optional admin, gate."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PLATFORM_GATE_MARKERS = (
    "coverage:",
    "eval_crosswalk row",
    "eval_crosswalk is empty",
    "near-duplicate",
    "crosswalk rows lack",
    "invented factor",
    "ungrounded row",
    "over-relies on one source chunk",
)

_TRUTHY_ENV = frozenset({"1", "true", "yes", "on"})
_MAX_PLATFORM_EXPAND_PASSES = 3


def _env_enabled(name: str) -> bool:
    return str(os.environ.get(name, "") or "").strip().lower() in _TRUTHY_ENV


def _scratchpad_has_grounded_evidence(run_dir: Path) -> bool:
    """True when retrieve phase left scratchpad chunk IDs for platform synthesis."""
    from src.skills.research_harness import _read_artifact

    scratchpad = _read_artifact(Path(run_dir), "research_scratchpad.md", max_chars=20_000)
    if len(scratchpad.strip()) < 500:
        return False
    return bool(
        re.findall(r"(?:doc-|chunk-|tb-)[a-zA-Z0-9_-]+", scratchpad, re.IGNORECASE)
    )


def _eval_needs_platform_expansion(run_dir: Path, workspace_dir: Path) -> bool:
    """True when handoff missing or crosswalk empty / below coverage contract."""
    from src.skills.evidence_gates import check_coverage_contract
    from src.skills.handoff_quality import _EVAL_COVERAGE_CONTRACT
    from src.skills.readiness_handoff_models import load_handoff_dict

    handoff_path = run_dir / "artifacts" / "eval_handoff.json"
    if not handoff_path.is_file():
        return True
    try:
        payload = load_handoff_dict(handoff_path)
    except (OSError, ValueError):
        return True
    crosswalk = payload.get("eval_crosswalk") or []
    if not isinstance(crosswalk, list) or not crosswalk:
        return True
    issues = check_coverage_contract(
        workspace_dir=workspace_dir,
        coverage_contract=_EVAL_COVERAGE_CONTRACT,
        artifact=payload,
    )
    return bool(issues)


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
    Platform eval pipeline node: repair, LLM crosswalk expansion when needed, validate.

    Chain retrieve-only leaves an empty crosswalk; platform expander fills rows from scratchpad.
    EVAL_EXPANDER_LLM=1 forces expansion even when coverage already passes.
    EVAL_ADMIN_LLM=1 opt-in acronym admin pass.

    Returns dict with keys: issues, retriable_issues, blocking_issues, warnings, passed.
    """
    warnings: list[str] = []

    from src.skills.eval_handoff_repair import repair_eval_handoff

    if repair_eval_handoff(run_dir):
        warnings.append("eval_finalize: repaired_known_acronyms")

    force_expand = _env_enabled("EVAL_EXPANDER_LLM")
    needs_expand = force_expand or (
        _eval_needs_platform_expansion(run_dir, workspace_dir)
        and _scratchpad_has_grounded_evidence(run_dir)
    )
    if needs_expand:
        from src.skills.eval_handoff_expander import expand_eval_handoff, expansion_satisfied

        for expand_pass in range(_MAX_PLATFORM_EXPAND_PASSES):
            try:
                payload, expand_warnings = await expand_eval_handoff(
                    run_dir=run_dir,
                    workspace_dir=workspace_dir,
                    loop_response=loop_response if expand_pass == 0 else "",
                )
                warnings.extend(expand_warnings)
                if not force_expand and expand_pass == 0:
                    warnings.append("eval_finalize: platform_expander_auto")
                if expansion_satisfied(workspace_dir=workspace_dir, payload=payload):
                    break
                if expand_pass + 1 < _MAX_PLATFORM_EXPAND_PASSES:
                    warnings.append(
                        f"eval_finalize: expand_pass_{expand_pass + 1}_below_coverage"
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("eval_finalize expand failed: %s", exc)
                warnings.append(f"eval_finalize: expand_failed: {exc}")
                break

        if repair_eval_handoff(run_dir):
            warnings.append("eval_finalize: repaired_known_acronyms_post_expand")

    handoff_path = run_dir / "artifacts" / "eval_handoff.json"
    if handoff_path.is_file() and _env_enabled("EVAL_ADMIN_LLM"):
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