from types import SimpleNamespace
import asyncio
import tomllib

from src.server.native_lightrag_runtime import build_native_lightrag_runtime, initialize_native_lightrag


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
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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