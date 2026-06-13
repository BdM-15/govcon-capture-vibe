"""Tests for external research intent routing."""

from __future__ import annotations

from src.server.briefing_prompts import BRIEFING_PROMPT_LIBRARY
from src.skills.external_research_intent import detect_external_research_intent
from src.skills.mission_readiness_chain import build_mission_readiness_chain_spec


def _mission_readiness_catalog_prompt() -> str:
    for entry in BRIEFING_PROMPT_LIBRARY:
        if entry.get("chain_preset") == "mission-readiness":
            return str(entry["prompt"])
    raise AssertionError("mission-readiness catalog prompt not found")


def test_catalog_prompt_does_not_trigger_external_research() -> None:
    prompt = _mission_readiness_catalog_prompt()
    assert detect_external_research_intent(prompt) is None


def test_generic_technology_mention_does_not_trigger_external_research() -> None:
    assert (
        detect_external_research_intent(
            "Identify innovation opportunities — methods not only technology."
        )
        is None
    )


def test_explicit_vendor_url_triggers_external_research() -> None:
    intent = detect_external_research_intent(
        "Review https://example.com/platform for Tagup, Inc applicability."
    )
    assert intent is not None
    assert intent.seed_urls
    assert "example.com/platform" in intent.seed_urls[0]


def test_explicit_overlay_phrase_triggers_external_research() -> None:
    intent = detect_external_research_intent(
        "Add a capability overlay for the incumbent SaaS platform."
    )
    assert intent is not None
    assert intent.requested is True


def test_chain_spec_omits_external_step_for_catalog_prompt_only() -> None:
    spec = build_mission_readiness_chain_spec(_mission_readiness_catalog_prompt())
    skills = [step.skill for step in spec.steps]
    assert "readiness-frame-external-research" not in skills
    assert spec.context.get("external_research") is False


def test_chain_spec_includes_external_step_from_user_addendum() -> None:
    spec = build_mission_readiness_chain_spec(
        _mission_readiness_catalog_prompt(),
        user_addendum="Review https://example.com/platform for Tagup, Inc.",
    )
    skills = [step.skill for step in spec.steps]
    assert "readiness-frame-external-research" in skills
    assert spec.context.get("external_research") is True