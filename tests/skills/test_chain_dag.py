"""Tests for skill-chain DAG scheduling."""

from __future__ import annotations

from src.skills.chain_dag import compute_execution_waves, transitive_dependent_ids
from src.skills.chain_models import ChainStepSpec
from src.skills.mission_readiness_chain import build_mission_readiness_chain_spec


def test_mission_readiness_chain_serial_micro_skill_waves() -> None:
    spec = build_mission_readiness_chain_spec(
        "Build the Mission Readiness Frame from the solicitation package."
    )
    waves = compute_execution_waves(spec)
    assert waves[0] == ["workload"]
    assert waves[1] == ["eval"]
    assert waves[2] == ["pains"]
    assert waves[3] == ["modernization"]
    assert waves[4] == ["tea-leaves"]
    assert waves[5] == ["win-themes"]
    assert waves[-1] == ["compile"]


def test_transitive_dependents_includes_compile() -> None:
    spec = build_mission_readiness_chain_spec("Build frame.")
    dependents = transitive_dependent_ids(spec, "workload")
    assert "eval" in dependents
    assert "tea-leaves" in dependents
    assert "win-themes" in dependents
    assert "compile" in dependents


def test_compute_execution_waves_raises_on_cycle() -> None:
    from src.skills.chain_models import ChainSpec

    spec = ChainSpec.model_construct(
        name="cycle",
        steps=[
            ChainStepSpec(id="a", skill="skill-a", depends_on=["b"]),
            ChainStepSpec(id="b", skill="skill-b", depends_on=["a"]),
        ],
    )
    try:
        compute_execution_waves(spec)
    except ValueError as exc:
        assert "dependency graph" in str(exc)
    else:
        raise AssertionError("expected cycle detection to fail")