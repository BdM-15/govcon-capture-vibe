"""Tests for mission-readiness Intel chain preset."""

from __future__ import annotations

from src.skills.chain_executor import SkillChainExecutor
from src.skills.chain_models import ChainRunState, ChainSpec, ChainStepRun, ChainStepSpec
from src.skills.mission_readiness_chain import build_mission_readiness_chain_spec


def test_build_mission_readiness_chain_spec_orders_micro_skills_before_compiler() -> None:
    spec = build_mission_readiness_chain_spec(
        "Build the Mission Readiness Frame from the solicitation package."
    )
    skills = [step.skill for step in spec.steps]
    assert skills[-1] == "mission-readiness-framer"
    assert skills[0:2] == ["readiness-frame-workload", "readiness-frame-eval"]
    assert "readiness-frame-win-themes" in skills
    assert "readiness-frame-external-research" not in skills
    assert spec.name == "mission-readiness-chain"
    assert spec.context.get("external_research") is False


def test_compile_step_depends_only_on_terminal_slices() -> None:
    spec = build_mission_readiness_chain_spec(
        "Build the Mission Readiness Frame from the solicitation package."
    )
    compile_step = spec.steps[-1]
    assert compile_step.depends_on == ["win-themes"]


def test_compile_step_requires_six_handoff_artifacts() -> None:
    spec = build_mission_readiness_chain_spec(
        "Build the Mission Readiness Frame from the solicitation package."
    )
    compile_step = spec.steps[-1]
    assert compile_step.id == "compile"
    assert compile_step.context.get("role") == "compiler"
    assert len(compile_step.artifact_requirements) == 6
    requirement_ids = {req.id for req in compile_step.artifact_requirements}
    assert requirement_ids == {
        "eval-handoff",
        "workload-handoff",
        "pains-handoff",
        "modernization-handoff",
        "tea-leaves-handoff",
        "win-themes-handoff",
    }


def test_build_mission_readiness_chain_includes_external_step_from_addendum() -> None:
    spec = build_mission_readiness_chain_spec(
        "Build the Mission Readiness Frame from the solicitation package.",
        user_addendum="Review https://example.com/platform for Tagup applicability.",
    )
    skills = [step.skill for step in spec.steps]
    assert "readiness-frame-external-research" in skills
    compile_step = spec.steps[-1]
    assert set(compile_step.depends_on) == {"external", "win-themes"}


def test_retry_gap_prompt_snippet_is_compact_json() -> None:
    step = ChainStepSpec(
        id="eval",
        skill="readiness-frame-eval",
        prompt="Build eval crosswalk.",
        context={
            "platform_gate_gaps": [
                "coverage: eval_crosswalk 8/24 required",
                "undefined acronyms: TECV, SB",
            ],
            "retrieve_retry": 1,
        },
    )
    chain = ChainRunState(
        chain_id="chain-1",
        workspace="ws",
        status="running",
        spec=ChainSpec(name="mission-readiness", prompt="Build MRF.", steps=[step]),
        steps={"eval": ChainStepRun(id="eval", skill="readiness-frame-eval", status="running")},
    )
    prompt = SkillChainExecutor._compose_step_prompt(chain, step)
    gap_section = prompt.split("## Platform gate gaps", maxsplit=1)[1].split(
        "## Theseus Chain Handoff", maxsplit=1
    )[0]
    assert len(gap_section) < 500
    assert '"gate_gaps"' in gap_section
    assert "coverage:" in gap_section
    assert "undefined acronyms" in gap_section