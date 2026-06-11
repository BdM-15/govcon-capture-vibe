from src.skills.coverage_boost import (
    apply_coverage_boost,
    detect_exhaustive_coverage_intent,
)


def test_detect_exhaustive_coverage_intent_matches_workspace_wide_prompts() -> None:
    assert detect_exhaustive_coverage_intent("Build a full task area map for this workspace")
    assert detect_exhaustive_coverage_intent("Complete requirement traceability crosswalk")
    assert detect_exhaustive_coverage_intent("Map all evaluation factors")


def test_detect_exhaustive_coverage_intent_ignores_focused_prompts() -> None:
    assert not detect_exhaustive_coverage_intent("Summarize Factor A approach")
    assert not detect_exhaustive_coverage_intent("")
    assert not detect_exhaustive_coverage_intent("Draft one infographic for staffing")


def test_apply_coverage_boost_widens_query_settings() -> None:
    settings = {
        "top_k": 40,
        "chunk_top_k": 20,
        "max_total_tokens": 60_000,
        "skill_max_entities_per_type": 80,
        "skill_max_chunks_per_entity": 10,
    }
    boosted, meta = apply_coverage_boost(settings)

    assert boosted["top_k"] > settings["top_k"]
    assert boosted["chunk_top_k"] > settings["chunk_top_k"]
    assert boosted["max_total_tokens"] > settings["max_total_tokens"]
    assert meta["coverage_boost_applied"] is True