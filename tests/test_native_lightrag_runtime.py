import asyncio
import os
import tomllib
from types import SimpleNamespace

from src.server.native_lightrag_runtime import (
    build_native_lightrag_runtime,
    configure_native_parser_environment,
    initialize_native_lightrag,
)


class _FakeLightRAG:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeEmbeddingFunc:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _settings(**overrides):
    values = {
        "workspace": "demo",
        "working_dir": "./rag_storage",
        "embedding_model": "text-embedding-3-large",
        "embedding_dim": 3072,
        "embedding_binding_api_key": "openai-key",
        "llm_binding_api_key": "xai-key",
        "llm_binding_host": "https://api.x.ai/v1",
        "llm_timeout": 300,
        "min_rerank_score": 0.25,
        "lightrag_parser": "pdf:mineru-ite,docx:native-ite",
        "mineru_api_mode": "local",
        "mineru_local_endpoint": "http://localhost:8888",
        "mineru_official_endpoint": "https://mineru.net",
        "mineru_api_token": None,
        "mineru_local_backend": "pipeline",
        "mineru_local_parse_method": "auto",
        "mineru_language": "en",
        "enable_image_processing": True,
        "enable_table_processing": True,
        "enable_equation_processing": False,
        "max_parallel_parse_native": 5,
        "max_parallel_parse_mineru": 2,
        "max_parallel_parse_docling": 1,
        "max_parallel_analyze": 4,
        "vlm_process_enable": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_configure_native_parser_environment_sets_lightrag_parser_and_mineru_env() -> None:
    env = {}
    validated = []

    parser = configure_native_parser_environment(
        _settings(),
        environ=env,
        validate_parser_routing_fn=lambda rules: validated.append(rules),
    )

    assert validated == ["pdf:mineru-ite,docx:native-ite"]
    assert env == {
        "LIGHTRAG_PARSER": "pdf:mineru-ite,docx:native-ite",
        "MINERU_API_MODE": "local",
        "MINERU_LOCAL_ENDPOINT": "http://localhost:8888",
        "MINERU_OFFICIAL_ENDPOINT": "https://mineru.net",
        "MINERU_LOCAL_BACKEND": "pipeline",
        "MINERU_LOCAL_PARSE_METHOD": "auto",
        "MINERU_LANGUAGE": "en",
        "MINERU_ENABLE_TABLE": "true",
        "MINERU_ENABLE_FORMULA": "false",
        "MINERU_LOCAL_IMAGE_ANALYSIS": "true",
        "VLM_PROCESS_ENABLE": "true",
        "MAX_PARALLEL_PARSE_NATIVE": "5",
        "MAX_PARALLEL_PARSE_MINERU": "2",
        "MAX_PARALLEL_PARSE_DOCLING": "1",
        "MAX_PARALLEL_ANALYZE": "4",
    }
    assert parser.routing == "pdf:mineru-ite,docx:native-ite"
    assert parser.mineru_api_mode == "local"
    assert parser.mineru_endpoint == "http://localhost:8888"
    assert parser.mineru_backend == "pipeline"
    assert parser.mineru_parse_method == "auto"
    assert parser.concurrency == {
        "native": 5,
        "mineru": 2,
        "docling": 1,
        "analyze": 4,
    }


def test_native_parser_routing_resolves_mineru_native_and_legacy_without_service(monkeypatch) -> None:
    from lightrag.parser.routing import resolve_file_parser_directives

    for key in (
        "LIGHTRAG_PARSER",
        "MINERU_API_MODE",
        "MINERU_LOCAL_ENDPOINT",
        "MINERU_OFFICIAL_ENDPOINT",
        "MINERU_LOCAL_BACKEND",
        "MINERU_LOCAL_PARSE_METHOD",
        "MINERU_LANGUAGE",
        "MINERU_ENABLE_TABLE",
        "MINERU_ENABLE_FORMULA",
        "MINERU_LOCAL_IMAGE_ANALYSIS",
        "VLM_PROCESS_ENABLE",
        "MAX_PARALLEL_PARSE_NATIVE",
        "MAX_PARALLEL_PARSE_MINERU",
        "MAX_PARALLEL_PARSE_DOCLING",
        "MAX_PARALLEL_ANALYZE",
    ):
        monkeypatch.setenv(key, "")

    parser = configure_native_parser_environment(_settings(), environ=os.environ)

    assert resolve_file_parser_directives("volume.pdf", parser_rules=parser.routing) == (
        "mineru",
        "ite",
    )
    assert resolve_file_parser_directives("attachment.docx", parser_rules=parser.routing) == (
        "native",
        "ite",
    )
    assert resolve_file_parser_directives("notes.txt", parser_rules=parser.routing) == (
        "legacy",
        "",
    )


def test_build_native_lightrag_runtime_constructs_direct_lightrag_and_health() -> None:
    def fake_role_routing(settings, *, xai_api_key, xai_base_url):
        assert xai_api_key == "xai-key"
        assert xai_base_url == "https://api.x.ai/v1"
        return SimpleNamespace(
            modal_llm_func="modal-llm",
            vision_model_func="vision-llm",
            role_llm_configs={"extract": "extract-cfg", "query": "query-cfg"},
            use_strict_schema=True,
        )

    runtime = build_native_lightrag_runtime(
        _settings(),
        graph_storage="Neo4JStorage",
        lightrag_cls=_FakeLightRAG,
        embed_factory=SimpleNamespace(func=lambda **kwargs: kwargs),
        embedding_func_cls=_FakeEmbeddingFunc,
        build_role_llm_routing_fn=fake_role_routing,
        get_default_catalog=lambda: SimpleNamespace(render_part_d=lambda: "PART D"),
        make_rerank_func=lambda: "rerank-func",
        native_pipeline_available_fn=lambda: True,
        version_resolver=lambda pkg: {"lightrag-hku": "1.5.0rc3"}[pkg],
    )

    assert runtime.adapter.lightrag.kwargs["working_dir"] == "./rag_storage"
    assert runtime.adapter.lightrag.kwargs["workspace"] == "demo"
    assert runtime.adapter.lightrag.kwargs["graph_storage"] == "Neo4JStorage"
    assert runtime.adapter.lightrag.kwargs["role_llm_configs"] == {
        "extract": "extract-cfg",
        "query": "query-cfg",
    }
    assert runtime.adapter.llm_model_func == "modal-llm"
    assert runtime.adapter.vision_model_func == "vision-llm"
    assert runtime.health.native_pipeline_available is True
    assert runtime.health.lightrag_version == "1.5.0rc3"
    assert runtime.health.storage == {
        "kv": "JsonKVStorage",
        "vector": "NanoVectorDBStorage",
        "graph": "Neo4JStorage",
        "doc_status": "JsonDocStatusStorage",
    }
    assert runtime.health.roles == ["extract", "query"]
    assert runtime.health.multimodal == "native"


def test_build_native_lightrag_runtime_applies_parser_routing_to_lightrag_kwargs() -> None:
    parser_health = SimpleNamespace(
        routing="pdf:mineru-ite,docx:native-ite",
        mineru_api_mode="local",
        mineru_endpoint="http://localhost:8888",
        mineru_backend="pipeline",
        mineru_parse_method="auto",
        concurrency={"native": 5, "mineru": 2, "docling": 1, "analyze": 4},
    )

    runtime = build_native_lightrag_runtime(
        _settings(),
        graph_storage="NetworkXStorage",
        lightrag_cls=_FakeLightRAG,
        embed_factory=SimpleNamespace(func=lambda **kwargs: kwargs),
        embedding_func_cls=_FakeEmbeddingFunc,
        build_role_llm_routing_fn=lambda settings, **kwargs: SimpleNamespace(
            modal_llm_func="modal-llm",
            vision_model_func="vision-llm",
            role_llm_configs={"extract": "extract-cfg"},
        ),
        get_default_catalog=lambda: SimpleNamespace(render_part_d=lambda: "PART D"),
        make_rerank_func=lambda: None,
        native_pipeline_available_fn=lambda: True,
        version_resolver=lambda pkg: "1.5.0rc3",
        configure_native_parser_environment_fn=lambda settings: parser_health,
    )

    assert runtime.adapter.lightrag.kwargs["vlm_process_enable"] is True
    assert runtime.adapter.lightrag.kwargs["max_parallel_parse_native"] == 5
    assert runtime.adapter.lightrag.kwargs["max_parallel_parse_mineru"] == 2
    assert runtime.adapter.lightrag.kwargs["max_parallel_parse_docling"] == 1
    assert runtime.adapter.lightrag.kwargs["max_parallel_analyze"] == 4
    assert runtime.health.parser is parser_health


def test_initialize_native_lightrag_initializes_storages() -> None:
    calls = []
    prompt_map = {}
    govcon_prompts = {"rag_response": "mentor prompt"}

    class _LightRAGWithInit:
        async def initialize_storages(self):
            calls.append("initialize_storages")

    built_runtime = SimpleNamespace(
        adapter=SimpleNamespace(lightrag=_LightRAGWithInit()),
        health=SimpleNamespace(native_pipeline_available=True),
    )

    async def run():
        return await initialize_native_lightrag(
            _settings(),
            graph_storage="Neo4JStorage",
            build_runtime_fn=lambda settings, graph_storage: built_runtime,
            prompt_map=prompt_map,
            govcon_prompts=govcon_prompts,
        )

    initialized = asyncio.run(run())

    assert initialized is built_runtime
    assert calls == ["initialize_storages"]
    assert prompt_map == govcon_prompts


def test_initialize_native_lightrag_registers_native_multimodal_prompts() -> None:
    prompt_map = {}
    multimodal_prompt_map = {"table_analysis": "generic"}
    native_prompts = {"table_analysis": "govcon table", "image_analysis": "govcon image"}

    built_runtime = SimpleNamespace(
        adapter=SimpleNamespace(lightrag=SimpleNamespace()),
        health=SimpleNamespace(native_pipeline_available=True),
    )

    async def run():
        return await initialize_native_lightrag(
            _settings(),
            graph_storage="Neo4JStorage",
            build_runtime_fn=lambda settings, graph_storage: built_runtime,
            prompt_map=prompt_map,
            govcon_prompts={"rag_response": "mentor"},
            multimodal_prompt_map=multimodal_prompt_map,
            native_multimodal_prompts=native_prompts,
        )

    asyncio.run(run())

    assert multimodal_prompt_map == {
        "table_analysis": "govcon table",
        "image_analysis": "govcon image",
    }


def test_pyproject_pins_lightrag_to_native_multimodal_commit() -> None:
    with open("pyproject.toml", "rb") as file:
        pyproject = tomllib.load(file)

    dependencies = pyproject["project"]["dependencies"]
    sources = pyproject["tool"]["uv"]["sources"]

    assert "lightrag-hku>=1.5.0rc3" in dependencies
    assert sources["lightrag-hku"] == {
        "git": "https://github.com/HKUDS/LightRAG.git",
        "rev": "33b067ffadf1eee2655a7efe9c72de4f8c25cbab",
    }