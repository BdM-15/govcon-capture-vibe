"""Solo invoke and assess helpers for readiness-frame micro-skills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.skills.chain_models import ChainSpec, ChainStepRun, ChainStepSpec
from src.skills.handoff_quality import (
    _SKILL_EXPECTED_HANDOFF,
    step_quality_errors,
)
from src.skills.local_llm_admin import admin_llm_status
from src.skills.mission_readiness_chain import build_mission_readiness_chain_spec

READINESS_ADMIN_STEP_IDS = frozenset({"eval", "compile"})

READINESS_SOLO_STEP_IDS = frozenset(
    {
        "eval",
        "workload",
        "pains",
        "modernization",
        "tea-leaves",
        "win-themes",
        "external",
        "compile",
    }
)


def get_readiness_step_spec(
    step_id: str,
    prompt: str,
    *,
    user_addendum: str = "",
) -> ChainStepSpec:
    """Return one mission-readiness chain step by id."""
    normalized = str(step_id or "").strip().lower()
    if normalized not in READINESS_SOLO_STEP_IDS:
        raise KeyError(f"unknown readiness step_id: {step_id}")
    spec = build_mission_readiness_chain_spec(prompt, user_addendum=user_addendum)
    for step in spec.steps:
        if step.id == normalized:
            return step
    raise KeyError(f"unknown readiness step_id: {step_id}")


def build_readiness_solo_chain_spec(
    step_id: str,
    prompt: str,
    *,
    user_addendum: str = "",
) -> ChainSpec:
    """Build a one-step chain spec for solo readiness micro-skill validation."""
    full_spec = build_mission_readiness_chain_spec(prompt, user_addendum=user_addendum)
    step = get_readiness_step_spec(step_id, prompt, user_addendum=user_addendum)
    return ChainSpec(
        name=f"solo-{step.id}",
        prompt=full_spec.prompt,
        context={
            "preset": "readiness-solo",
            "solo_step_id": step.id,
        },
        steps=[step],
        stop_on_error=True,
    )


def readiness_step_requires_admin_llm(step_id: str) -> bool:
    return str(step_id or "").strip().lower() in READINESS_ADMIN_STEP_IDS


def preflight_readiness_solo(step_id: str) -> str | None:
    """Return user-facing error when admin Ollama required but not ready; else None."""
    if not readiness_step_requires_admin_llm(step_id):
        return None
    status = admin_llm_status()
    if status.get("ready"):
        return None
    host = status.get("host") or "Ollama"
    model = status.get("model") or "configured model"
    state = status.get("state") or "unavailable"
    detail = status.get("error") or state
    hint = status.get("fix_hint") or "Start Ollama and confirm Settings host/model."
    return (
        f"Step '{step_id}' needs Ollama admin LLM ({host}, {model}) but state={state} ({detail}). "
        f"{hint}"
    )


def chain_spec_requires_admin_llm(spec: ChainSpec) -> bool:
    admin_skills = {"readiness-frame-eval", "mission-readiness-framer"}
    return any(step.skill in admin_skills for step in spec.steps)


def preflight_readiness_chain(spec: ChainSpec) -> str | None:
    if not chain_spec_requires_admin_llm(spec):
        return None
    status = admin_llm_status()
    if status.get("ready"):
        return None
    host = status.get("host") or "Ollama"
    model = status.get("model") or "configured model"
    state = status.get("state") or "unavailable"
    detail = status.get("error") or state
    hint = status.get("fix_hint") or "Start Ollama and confirm Settings host/model."
    return (
        f"Chain needs Ollama admin LLM for eval/compile finalize ({host}, {model}) "
        f"but state={state} ({detail}). {hint}"
    )


def build_solo_invoke_http_payload(
    step_id: str,
    prompt: str,
    *,
    user_addendum: str = "",
) -> dict[str, Any]:
    """HTTP body for POST /api/ui/skill-chains/invoke (readiness-solo preset)."""
    return {
        "preset": "readiness-solo",
        "solo_step_id": step_id,
        "name": f"solo-{step_id}",
        "prompt": prompt,
        "user_addendum": user_addendum,
        "stop_on_error": True,
    }


@dataclass(frozen=True)
class SoloReadinessAssessResult:
    step_id: str
    skill: str
    passed: bool
    errors: list[str]
    handoff_path: str = ""


def assess_readiness_solo_step(
    *,
    step_id: str,
    run_dir: Path,
    workspace_root: Path,
    finish_reason: str = "stop",
    warnings: list[str] | None = None,
) -> SoloReadinessAssessResult:
    """Deterministic solo gate for one readiness-frame step run directory."""
    step = get_readiness_step_spec(step_id, "")
    skill = step.skill
    handoff_name = _SKILL_EXPECTED_HANDOFF.get(skill, "")
    handoff_path = ""
    if handoff_name:
        candidate = run_dir / "artifacts" / handoff_name
        if candidate.is_file():
            handoff_path = str(candidate)

    step_run = ChainStepRun(
        id=step_id,
        skill=skill,
        status="completed",
        run_dir=str(run_dir),
    )
    errors = step_quality_errors(
        finish_reason=finish_reason,
        warnings=warnings,
        step_run=step_run,
        workspace_root=workspace_root,
    )
    return SoloReadinessAssessResult(
        step_id=step_id,
        skill=skill,
        passed=not errors,
        errors=errors,
        handoff_path=handoff_path,
    )


__all__ = [
    "READINESS_ADMIN_STEP_IDS",
    "READINESS_SOLO_STEP_IDS",
    "SoloReadinessAssessResult",
    "assess_readiness_solo_step",
    "build_readiness_solo_chain_spec",
    "build_solo_invoke_http_payload",
    "chain_spec_requires_admin_llm",
    "get_readiness_step_spec",
    "preflight_readiness_chain",
    "preflight_readiness_solo",
    "readiness_step_requires_admin_llm",
]