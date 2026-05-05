from types import SimpleNamespace

from src.server.initialization_support import (
    GovconInitializationRuntime,
    build_embedding_function,
    build_govcon_lightrag_setup,
    build_lightrag_runtime_kwargs,
    build_raganything_runtime,
    build_raganything_config,
    configure_mineru_environment,
)


class _FakeConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeEmbeddingFunc:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _settings(**overrides):
    values = {
        "workspace": "demo",
        "parser": "mineru",
        "parse_method": "auto",
        "enable_image_processing": True,
        "enable_table_processing": True,
        "enable_equation_processing": False,
        "mineru_device_mode": "cuda",
        "mineru_table_merge_enable": False,
        "embedding_model": "text-embedding-3-large",
        "embedding_dim": 3072,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_configure_mineru_environment_sets_expected_env() -> None:
    env = {}
    configure_mineru_environment(_settings(mineru_table_merge_enable=True), environ=env)

    assert env == {
        "MINERU_DEVICE_MODE": "cuda",
        "MINERU_TABLE_MERGE_ENABLE": "1",
    }


def test_build_raganything_config_creates_output_dir_and_kwargs(tmp_path) -> None:
    created = []

    def fake_makedirs(path, exist_ok=False):
        created.append((path, exist_ok))

    config, output_dir = build_raganything_config(
        _settings(workspace="ws-a"),
        working_dir=str(tmp_path),
        config_cls=_FakeConfig,
        makedirs=fake_makedirs,
    )

    assert output_dir.endswith("ws-a\\mineru") or output_dir.endswith("ws-a/mineru")
    assert created == [(output_dir, True)]
    assert config.kwargs["working_dir"] == str(tmp_path)
    assert config.kwargs["parser_output_dir"] == output_dir
    assert config.kwargs["enable_equation_processing"] is False


def test_build_embedding_function_uses_unwrapped_embed_impl() -> None:
    captured = {}

    def fake_embed_impl(**kwargs):
        captured.update(kwargs)
        return "embed-result"

    fake_factory = SimpleNamespace(func=fake_embed_impl)
    embedding = build_embedding_function(
        _settings(),
        openai_api_key="key-123",
        embed_factory=fake_factory,
        embedding_func_cls=_FakeEmbeddingFunc,
    )

    assert embedding.kwargs["embedding_dim"] == 3072
    assert embedding.kwargs["max_token_size"] == 8192
    assert embedding.kwargs["func"]()
    assert captured == {
        "model": "text-embedding-3-large",
        "api_key": "key-123",
        "max_token_size": 8192,
    }


def test_build_lightrag_runtime_kwargs_includes_optional_features() -> None:
    runtime_kwargs = build_lightrag_runtime_kwargs(
        entity_types_guidance="PART D",
        chunking_func="chunker",
        llm_timeout=600,
        role_llm_configs={"extract": "cfg"},
        rerank_func="rerank",
        min_rerank_score=0.42,
        graph_storage="Neo4JStorage",
    )

    assert runtime_kwargs == {
        "addon_params": {
            "entity_types_guidance": "PART D",
            "entity_type_prompt_file": "govcon.yaml",
            "language": "English",
        },
        "chunking_func": "chunker",
        "default_llm_timeout": 600,
        "role_llm_configs": {"extract": "cfg"},
        "rerank_model_func": "rerank",
        "min_rerank_score": 0.42,
        "graph_storage": "Neo4JStorage",
    }


def test_build_lightrag_runtime_kwargs_omits_optional_features_when_disabled() -> None:
    runtime_kwargs = build_lightrag_runtime_kwargs(
        entity_types_guidance="PART D",
        chunking_func="chunker",
        llm_timeout=300,
        role_llm_configs={"query": "cfg"},
        rerank_func=None,
        min_rerank_score=0.42,
        graph_storage="NetworkXStorage",
    )

    assert runtime_kwargs == {
        "addon_params": {
            "entity_types_guidance": "PART D",
            "entity_type_prompt_file": "govcon.yaml",
            "language": "English",
        },
        "chunking_func": "chunker",
        "default_llm_timeout": 300,
        "role_llm_configs": {"query": "cfg"},
    }


def test_build_govcon_lightrag_setup_assembles_runtime_inputs() -> None:
    def fake_chunker():
        return None

    fake_chunker.__name__ = "govcon_chunking_func"

    setup = build_govcon_lightrag_setup(
        _settings(min_rerank_score=0.33),
        llm_timeout=700,
        role_llm_configs={"extract": "cfg"},
        graph_storage="Neo4JStorage",
        get_default_catalog=lambda: SimpleNamespace(render_part_d=lambda: "PART D"),
        make_rerank_func=lambda: "rerank",
        chunking_func=fake_chunker,
        banner_template="[GOVCON_DOC]",
    )

    assert setup["banner_template"] == "[GOVCON_DOC]"
    assert setup["chunking_func"] is fake_chunker
    assert setup["chunking_func_name"] == "govcon_chunking_func"
    assert setup["entity_types_guidance"] == "PART D"
    assert setup["rerank_func"] == "rerank"
    assert setup["lightrag_kwargs"] == {
        "entity_extraction_use_json": True,
        "addon_params": {
            "entity_types_guidance": "PART D",
            "entity_type_prompt_file": "govcon.yaml",
            "language": "English",
        },
        "chunking_func": fake_chunker,
        "default_llm_timeout": 700,
        "role_llm_configs": {"extract": "cfg"},
        "rerank_model_func": "rerank",
        "min_rerank_score": 0.33,
        "graph_storage": "Neo4JStorage",
    }


def test_build_raganything_runtime_assembles_runtime_bundle() -> None:
    calls = []

    def fake_configure_mineru_environment(settings) -> None:
        calls.append(("configure_mineru_environment", settings.workspace))

    def fake_build_raganything_config(settings, *, working_dir, config_cls):
        calls.append(("build_raganything_config", working_dir, config_cls))
        return ("config-obj", working_dir + "/mineru")

    def fake_build_role_llm_routing(settings, *, xai_api_key, xai_base_url):
        calls.append(("build_role_llm_routing", xai_api_key, xai_base_url))
        return SimpleNamespace(
            modal_llm_func="modal-llm",
            vision_model_func="vision-llm",
            use_strict_schema=True,
            role_llm_configs={"extract": "cfg"},
        )

    def fake_build_embedding_function(settings, *, openai_api_key, embed_factory, embedding_func_cls):
        calls.append(("build_embedding_function", openai_api_key, embed_factory, embedding_func_cls))
        return "embedding-func"

    def fake_build_govcon_lightrag_setup(settings, *, llm_timeout, role_llm_configs, graph_storage):
        calls.append(("build_govcon_lightrag_setup", llm_timeout, role_llm_configs, graph_storage))
        return {
            "lightrag_kwargs": {"entity_extraction_use_json": True},
            "banner_template": "[GOVCON_DOC]",
            "chunking_func_name": "govcon_chunking_func",
        }

    runtime = build_raganything_runtime(
        _settings(llm_timeout=700),
        working_dir="./rag_storage/demo",
        xai_api_key="xai-key",
        xai_base_url="https://api.x.ai/v1",
        openai_api_key="openai-key",
        config_cls=_FakeConfig,
        embed_factory="embed-factory",
        embedding_func_cls=_FakeEmbeddingFunc,
        graph_storage="Neo4JStorage",
        configure_mineru_environment_fn=fake_configure_mineru_environment,
        build_raganything_config_fn=fake_build_raganything_config,
        build_role_llm_routing_fn=fake_build_role_llm_routing,
        build_embedding_function_fn=fake_build_embedding_function,
        build_govcon_lightrag_setup_fn=fake_build_govcon_lightrag_setup,
    )

    assert runtime == GovconInitializationRuntime(
        config="config-obj",
        mineru_output_dir="./rag_storage/demo/mineru",
        modal_llm_func="modal-llm",
        vision_model_func="vision-llm",
        use_strict_schema=True,
        embedding_func="embedding-func",
        lightrag_kwargs={"entity_extraction_use_json": True},
        banner_template="[GOVCON_DOC]",
        chunking_func_name="govcon_chunking_func",
    )
    assert calls == [
        ("configure_mineru_environment", "demo"),
        ("build_raganything_config", "./rag_storage/demo", _FakeConfig),
        ("build_role_llm_routing", "xai-key", "https://api.x.ai/v1"),
        ("build_embedding_function", "openai-key", "embed-factory", _FakeEmbeddingFunc),
        ("build_govcon_lightrag_setup", 700, {"extract": "cfg"}, "Neo4JStorage"),
    ]