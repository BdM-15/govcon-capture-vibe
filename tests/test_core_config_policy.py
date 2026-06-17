from types import SimpleNamespace

import pytest

from src.core.config import (
    Settings,
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


def test_settings_exposes_native_lightrag_parser_env_names() -> None:
    settings = Settings(
        LIGHTRAG_PARSER="pdf:mineru-ite,docx:native-ite",
        MINERU_API_MODE="official",
        MINERU_OFFICIAL_ENDPOINT="https://mineru.example",
        MINERU_API_TOKEN="mineru-token",
        MINERU_LOCAL_BACKEND="pipeline",
        MINERU_LOCAL_PARSE_METHOD="ocr",
        MINERU_LANGUAGE="en",
        MAX_PARALLEL_PARSE_NATIVE=6,
        MAX_PARALLEL_PARSE_MINERU=3,
        MAX_PARALLEL_PARSE_DOCLING=2,
        MAX_PARALLEL_ANALYZE=8,
        VLM_PROCESS_ENABLE=True,
        CHUNK_SIZE=4096,
        CHUNK_OVERLAP_SIZE=600,
    )

    assert settings.lightrag_parser == "pdf:mineru-ite,docx:native-ite"
    assert settings.mineru_api_mode == "official"
    assert settings.mineru_official_endpoint == "https://mineru.example"
    assert settings.mineru_api_token == "mineru-token"
    assert settings.mineru_local_backend == "pipeline"
    assert settings.mineru_local_parse_method == "ocr"
    assert settings.mineru_language == "en"
    assert settings.max_parallel_parse_native == 6
    assert settings.max_parallel_parse_mineru == 3
    assert settings.max_parallel_parse_docling == 2
    assert settings.max_parallel_analyze == 8
    assert settings.vlm_process_enable is True


def test_settings_exposes_mineru_stack_version_from_env() -> None:
    settings = Settings(
        MINERU_STACK_VERSION="3.3",
        CHUNK_SIZE=4096,
        CHUNK_OVERLAP_SIZE=600,
    )
    assert settings.mineru_stack_version == "3.3"


def test_settings_exposes_mineru_local_effort_default_and_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MINERU_LOCAL_EFFORT", raising=False)
    settings = Settings(
        _env_file=None,
        MINERU_LOCAL_EFFORT="high",
        CHUNK_SIZE=4096,
        CHUNK_OVERLAP_SIZE=600,
    )
    assert settings.mineru_local_effort == "high"

    # Field default is high when env/.env do not set MINERU_LOCAL_EFFORT
    settings2 = Settings(
        _env_file=None,
        CHUNK_SIZE=4096,
        CHUNK_OVERLAP_SIZE=600,
    )
    assert settings2.mineru_local_effort == "high"
