from types import SimpleNamespace

import pytest

from src.core.config import (
    effective_async,
    missing_required_settings_errors,
    validate_required_settings,
)


def test_effective_async_prefers_global_override() -> None:
    assert effective_async(None, 8) == 8
    assert effective_async(16, 8) == 16


def test_missing_required_settings_errors_collects_expected_fields() -> None:
    settings = SimpleNamespace(
        llm_binding_api_key=None,
        embedding_binding_api_key=None,
        chunk_size=None,
        chunk_overlap_size=None,
        graph_storage="Neo4JStorage",
        neo4j_password=None,
    )

    errors = missing_required_settings_errors(settings)

    assert errors == [
        "LLM_BINDING_API_KEY is required",
        "EMBEDDING_BINDING_API_KEY is required",
        "CHUNK_SIZE is required (no safe default exists)",
        "CHUNK_OVERLAP_SIZE is required (no safe default exists)",
        "NEO4J_PASSWORD is required when using Neo4JStorage",
    ]


def test_validate_required_settings_raises_full_message() -> None:
    settings = SimpleNamespace(
        llm_binding_api_key=None,
        embedding_binding_api_key="embed",
        chunk_size=1024,
        chunk_overlap_size=None,
        graph_storage="NetworkXStorage",
        neo4j_password=None,
    )

    with pytest.raises(ValueError, match="LLM_BINDING_API_KEY is required"):
        validate_required_settings(settings)