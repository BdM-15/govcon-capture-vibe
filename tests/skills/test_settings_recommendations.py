"""Tests for workspace-size query tuning recommendations."""

from __future__ import annotations

from src.skills.settings_recommendations import recommend_query_settings


def test_recommend_small_workspace_tier() -> None:
    rec = recommend_query_settings(entity_count=200, chunk_count=500)
    assert rec["tier"] == "small"
    assert rec["recommended"]["top_k"] == 40


def test_recommend_xlarge_workspace_tier() -> None:
    rec = recommend_query_settings(entity_count=8000)
    assert rec["tier"] == "xlarge"
    assert rec["recommended"]["top_k"] == 100


def test_should_notify_when_current_differs() -> None:
    rec = recommend_query_settings(
        entity_count=3000,
        current={"top_k": 10, "chunk_top_k": 5},
    )
    assert rec["tier"] == "large"
    assert rec["should_notify"] is True
    assert "top_k" in rec["differs"]