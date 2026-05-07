"""Tests for dynamic skill chain planning."""

from __future__ import annotations

import pytest

from src.skills.chain_contracts import CONTRACT_REGISTRY, SkillChainContract
from src.skills.chain_planner import SkillChainPlanner


_SKILLS = [
    {
        "name": "competitive-intel",
        "description": "Research incumbents, competitors, awards, and obligations.",
        "capability": "research",
    },
    {
        "name": "workload-analyzer",
        "description": "Analyze workload spreadsheets and demand trends for pricing.",
        "capability": "analyze",
    },
    {
        "name": "price-to-win",
        "description": "Build federal price-to-win and should-cost estimates.",
        "capability": "estimate",
    },
    {
        "name": "proposal-generator",
        "description": "Draft proposal outlines, win themes, and compliance matrices.",
        "capability": "draft",
    },
    {
        "name": "rfp-reverse-engineer",
        "description": "Reverse engineer RFP scope and hot buttons.",
        "capability": "analyze",
    },
    {
        "name": "renderers",
        "description": "Render Markdown and JSON into DOCX and XLSX deliverables.",
        "capability": "render",
    },
    {
        "name": "caveman",
        "description": "Developer terse communication mode.",
        "capability": "meta",
    },
]


def test_planner_builds_logical_ptw_chain_with_rendering() -> None:
    planner = SkillChainPlanner(_SKILLS)

    plan = planner.plan(
        prompt="Build a price-to-win package using incumbent IDIQ obligations and workload data.",
        outcome="Excel workbook and brief",
    )

    skills = [step.skill for step in plan.spec.steps]
    assert skills == [
        "competitive-intel",
        "workload-analyzer",
        "price-to-win",
        "renderers",
    ]
    assert plan.spec.steps[2].depends_on == ["competitive-intel", "workload-analyzer"]
    assert plan.spec.steps[3].depends_on == ["price-to-win"]
    assert plan.spec.context["expected_outcome"] == "Excel workbook and brief"
    assert plan.iteration_policy["mode"] == "outcome-gated-linear"
    assert "low/mid/high" in plan.spec.steps[2].context["quality_gate"]


def test_planner_defaults_reverse_engineer_before_proposal() -> None:
    planner = SkillChainPlanner(_SKILLS)

    plan = planner.plan(
        prompt="Draft a proposal response with win themes and compliance matrix.",
        outcome="Proposal draft",
        include_rendering=False,
    )

    skills = [step.skill for step in plan.spec.steps]
    assert skills == ["rfp-reverse-engineer", "proposal-generator"]
    assert plan.spec.steps[1].depends_on == ["rfp-reverse-engineer"]


def test_planner_rejects_no_matching_skill() -> None:
    planner = SkillChainPlanner([])

    with pytest.raises(ValueError, match="No installed skill matches chain goal"):
        planner.plan(prompt="Build a proposal")


def test_contract_registry_defines_handoff_edges_and_artifacts() -> None:
    ptw = CONTRACT_REGISTRY.require("price-to-win")

    assert "obligation_data" in ptw.accepts
    assert "pricing_stack" in ptw.produces
    assert CONTRACT_REGISTRY.upstream_skills("price-to-win") == (
        "competitive-intel",
        "workload-analyzer",
    )
    assert CONTRACT_REGISTRY.default_upstream(
        "competitive-intel",
        "price-to-win",
        {"ptw"},
    )


def test_contract_model_rejects_unknown_top_level_fields() -> None:
    with pytest.raises(ValueError):
        SkillChainContract(skill="demo", unsupported=True)  # type: ignore[call-arg]
