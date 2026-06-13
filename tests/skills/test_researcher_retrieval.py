"""Tests for researcher-grade aquery_data retrieval passthrough."""

from __future__ import annotations

import pytest

from src.skills.researcher_retrieval import (
    build_retrieval_query,
    format_grounded_context_for_scratchpad,
    retrieve_grounded_context_for_researcher_artifact,
    shape_grounded_payload,
)


def test_build_retrieval_query_composes_prompt_and_skill() -> None:
    query = build_retrieval_query("Build eval cross-walk", "Mission readiness framer")
    assert "Build eval cross-walk" in query
    assert "Mission readiness framer" in query


def test_shape_grounded_payload_preserves_full_context() -> None:
    raw = {
        "status": "success",
        "data": {
            "entities": [{"entity_name": "Technical Approach", "entity_type": "evaluation_factor"}],
            "relationships": [{"src_id": "a", "tgt_id": "b", "description": "links"}],
            "chunks": [{"chunk_id": "chunk-abc", "content": "The contractor shall maintain readiness."}],
            "references": [{"ref_id": "r1"}],
        },
    }
    shaped = shape_grounded_payload(raw, top_k=40)
    assert len(shaped["entities"]) == 1
    assert len(shaped["chunks"]) == 1
    assert "technical approach" in shaped["names"]
    assert "chunk-abc" in shaped["chunk_ids"]


def test_format_grounded_context_includes_entities_and_chunks() -> None:
    grounded = shape_grounded_payload(
        {
            "data": {
                "entities": [{"entity_name": "Factor A", "entity_type": "evaluation_factor", "description": "desc"}],
                "chunks": [{"chunk_id": "chunk-1", "content": "Verbatim government language here."}],
            }
        },
        top_k=10,
    )
    text = format_grounded_context_for_scratchpad(grounded, query="eval factors")
    assert "Bootstrap retrieval" in text
    assert "Factor A" in text
    assert "chunk-1" in text
    assert "Verbatim government" in text


@pytest.mark.asyncio
async def test_retrieve_grounded_context_returns_empty_when_mode_off() -> None:
    result = await retrieve_grounded_context_for_researcher_artifact(
        None,
        prompt="test",
        skill_description="desc",
        mode="off",
        query_overrides={"top_k": 20},
    )
    assert result["metadata"]["used"] is False
    assert result["metadata"]["reason"] == "retrieval disabled (mode=off)"


@pytest.mark.asyncio
async def test_retrieve_grounded_context_calls_data_func() -> None:
    async def fake_data_func(query, mode, history, overrides):
        return {
            "data": {
                "entities": [{"entity_name": "QASP", "entity_type": "performance_standard"}],
                "chunks": [{"chunk_id": "chunk-qasp", "content": "Inspection criteria."}],
            }
        }

    result = await retrieve_grounded_context_for_researcher_artifact(
        fake_data_func,
        prompt="QASP standards",
        skill_description="workload skill",
        mode="hybrid",
        query_overrides={"top_k": 30},
    )
    assert result["metadata"]["used"] is True
    assert result["metadata"]["matched_chunks"] == 1
    assert "chunk-qasp" in result["chunk_ids"]