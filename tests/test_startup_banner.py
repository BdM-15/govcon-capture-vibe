from types import SimpleNamespace

from src.theseus_server import build_startup_banner_items, format_reranker_line
from src.server.native_lightrag_runtime import NativeParserHealth, NativePipelineHealth


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
        version_resolver=lambda pkg: {"mineru": "1.2.3", "lightrag-hku": "2.0.0"}[pkg],
    )

    labels = [label for label, _ in items]
    assert "Workspace" in labels
    assert "Schema" in labels
    assert "WebUI" in labels
    assert "Capture Workbench" in labels
    assert "Neo4j" in labels
    assert any("33" in value and "35" in value for label, value in items if label == "Schema")


def test_build_startup_banner_items_reports_langgraph_studio_state() -> None:
    items = build_startup_banner_items(
        _settings(),
        host="127.0.0.1",
        port=9621,
        graph_storage="Neo4JStorage",
        working_dir="rag_storage/demo",
        entity_count=33,
        relationship_count=35,
        colors=_Colors,
        langgraph_studio_status={
            "ok": True,
            "graph_url": "https://smith.langchain.com/studio/?baseUrl=http%3A//127.0.0.1%3A2024&graph=mission_readiness",
            "version": "1.2.5",
        },
    )

    langgraph_row = next(value for label, value in items if label == "LangGraph")
    assert "1.2.5" in langgraph_row
    assert "mission_readiness" in langgraph_row


def test_build_startup_banner_items_reports_ollama_warmup_state() -> None:
    items = build_startup_banner_items(
        _settings(),
        host="127.0.0.1",
        port=9621,
        graph_storage="Neo4JStorage",
        working_dir="rag_storage/demo",
        entity_count=33,
        relationship_count=35,
        colors=_Colors,
        ollama_status={"ok": True, "state": "ready", "model": "qwen3.5:9b"},
    )

    ollama_row = next(value for label, value in items if label == "Ollama   (local)")
    assert "qwen3.5:9b" in ollama_row
    assert "READY" in ollama_row


def test_build_startup_banner_items_reports_native_pipeline_health() -> None:
    items = build_startup_banner_items(
        _settings(),
        host="127.0.0.1",
        port=9621,
        graph_storage="Neo4JStorage",
        working_dir="rag_storage/demo",
        entity_count=33,
        relationship_count=35,
        colors=_Colors,
        version_resolver=lambda pkg: {"mineru": "1.2.3", "lightrag-hku": "1.5.2"}[pkg],
        pipeline_health=NativePipelineHealth(
            lightrag_version="1.5.2",
            native_pipeline_available=True,
            roles=["extract", "keyword", "query", "vlm"],
            storage={
                "kv": "JsonKVStorage",
                "vector": "NanoVectorDBStorage",
                "graph": "Neo4JStorage",
                "doc_status": "JsonDocStatusStorage",
            },
            multimodal="native",
            parser=NativeParserHealth(
                routing="pdf:mineru-ite,docx:native-ite",
                mineru_api_mode="local",
                mineru_endpoint="http://localhost:8888",
                mineru_backend="pipeline",
                mineru_parse_method="auto",
                concurrency={"native": 5, "mineru": 2, "docling": 1, "analyze": 4},
            ),
        ),
    )

    values = "\n".join(value for _, value in items)
    labels = [label for label, _ in items]
    assert "Runtime" in labels
    assert any("LightRAG-first" in value for label, value in items if label == "Runtime")
    assert "Native Pipeline" in labels
    assert "Role Registry" in labels
    assert "Storage Detail" in labels
    assert "Schema" in labels
    assert "RAG-Anything" not in labels
    assert "Parser Routing" in labels
    assert "MinerU Mode" in labels
    assert "Parser Workers" in labels
    assert "1.5.2" in values
    assert "extract, keyword, query, vlm" in values
    assert "JsonKVStorage" in values
    assert "pdf:mineru-ite,docx:native-ite" in values
    assert "local" in values
    assert "pipeline" in values
    assert "mineru=2" in values