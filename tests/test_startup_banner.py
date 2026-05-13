from types import SimpleNamespace

from src.raganything_server import build_startup_banner_items, format_reranker_line


class _Colors:
    BOLD = "<b>"
    WHITE = "<w>"
    RESET = "</>"
    YELLOW = "<y>"
    DIM = "<d>"
    CYAN = "<c>"
    MAGENTA = "<m>"
    GREEN = "<g>"
    BLUE = "<bl>"


def _settings(**overrides):
    values = {
        "workspace": "demo",
        "extraction_llm_name": "extract-model",
        "keyword_llm_name": "keyword-model",
        "vlm_llm_name": "vlm-model",
        "reasoning_llm_name": "reason-model",
        "post_processing_llm_name": "post-model",
        "embedding_model": "embed-model",
        "embedding_dim": 3072,
        "enable_rerank": True,
        "rerank_device": "cuda",
        "rerank_use_fp16": True,
        "rerank_model": "bge-reranker",
        "min_rerank_score": 0.33,
        "mineru_device_mode": "cuda",
        "parse_method": "auto",
        "vault_curation_llm_model": "qwen3.5:9b",
        "vault_curation_llm_host": "http://localhost:11434/v1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_format_reranker_line_handles_enabled_and_disabled() -> None:
    enabled = format_reranker_line(_settings(), _Colors)
    disabled = format_reranker_line(_settings(enable_rerank=False), _Colors)

    assert "bge-reranker" in enabled
    assert "FP16" in enabled
    assert "0.33" in enabled
    assert disabled == "<d>disabled</>"


def test_build_startup_banner_items_includes_endpoints_and_optional_neo4j() -> None:
    items = build_startup_banner_items(
        _settings(),
        host="127.0.0.1",
        port=9621,
        graph_storage="Neo4JStorage",
        working_dir="rag_storage/demo",
        entity_count=33,
        relationship_count=35,
        colors=_Colors,
        version_resolver=lambda pkg: {"mineru": "1.2.3", "lightrag-hku": "2.0.0", "raganything": "3.0.0"}[pkg],
        ollama_available=True,
    )

    labels = [label for label, _ in items]
    assert "Workspace" in labels
    assert "Schema" in labels
    assert "WebUI" in labels
    assert "Capture UI" in labels
    assert "Neo4j" in labels
    assert any("33" in value and "35" in value for label, value in items if label == "Schema")
    assert "Vault Curation" in labels
    assert any("qwen3.5:9b" in value for label, value in items if label == "Vault Curation")


def test_build_startup_banner_ollama_unavailable_shows_offline() -> None:
    items = build_startup_banner_items(
        _settings(),
        host="127.0.0.1",
        port=9621,
        graph_storage="Neo4JStorage",
        working_dir="rag_storage/demo",
        entity_count=33,
        relationship_count=35,
        colors=_Colors,
        version_resolver=lambda pkg: {"mineru": "1.2.3", "lightrag-hku": "2.0.0", "raganything": "3.0.0"}[pkg],
        ollama_available=False,
    )
    vault_values = [value for label, value in items if label == "Vault Curation"]
    assert vault_values, "Vault Curation row must be present even when Ollama is offline"
    assert any("offline" in v.lower() or "unavailable" in v.lower() or "disabled" in v.lower() for v in vault_values)