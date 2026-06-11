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
        "name": "mission-readiness-framer",
        "description": "Frame mission readiness and program-office customer intent.",
        "capability": "analyze",
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
    ptw_products = {
        product
        for requirement in plan.spec.steps[2].artifact_requirements
        for product in requirement.products
    }
    assert {"obligation_data", "pricing_inputs"}.issubset(ptw_products)
    assert plan.spec.context["expected_outcome"] == "Excel workbook and brief"
    assert plan.iteration_policy["mode"] == "outcome-gated-linear"
    assert "low/mid/high" in plan.spec.steps[2].context["quality_gate"]


def test_planner_defaults_mission_readiness_framer_before_proposal() -> None:
    planner = SkillChainPlanner(_SKILLS)

    plan = planner.plan(
        prompt="Draft a proposal response with win themes and compliance matrix.",
        outcome="Proposal draft",
        include_rendering=False,
    )

    skills = [step.skill for step in plan.spec.steps]
    assert skills == ["mission-readiness-framer", "proposal-generator"]
    assert plan.spec.steps[1].depends_on == ["mission-readiness-framer"]
    assert plan.spec.steps[0].context["retrieval_query"]
    assert plan.spec.steps[1].context["ask_for_input_when_missing"] is True


def test_planner_routes_content_brief_to_content_skill_instead_of_renderer_only() -> None:
    planner = SkillChainPlanner(_SKILLS)

    plan = planner.plan(
        prompt="Competitive intel brief",
        outcome="DOCX brief",
    )

    assert [step.skill for step in plan.spec.steps] == ["competitive-intel"]


def test_planner_allows_renderer_only_for_explicit_render_request() -> None:
    planner = SkillChainPlanner(_SKILLS)

    plan = planner.plan(
        prompt="Render existing markdown artifact to DOCX",
        outcome="DOCX",
    )

    assert [step.skill for step in plan.spec.steps] == ["renderers"]


def test_planner_embeds_step_scoped_retrieval_hints() -> None:
    planner = SkillChainPlanner(_SKILLS)

    plan = planner.plan(
        prompt="Build a price to win package using incumbent obligations",
        outcome="Excel workbook and brief",
    )

    ptw_step = next(step for step in plan.spec.steps if step.skill == "price-to-win")
    assert plan.spec.context["retrieval_strategy"] == "step-scoped-hints"
    assert plan.spec.context["hitl_mode"] == "resume-after-missing-input"
    assert "retrieval_query" in ptw_step.context
    assert "pricing_stack" in ptw_step.context["retrieval_focus"]


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
