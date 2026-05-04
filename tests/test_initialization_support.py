from types import SimpleNamespace

from src.server.initialization_support import (
    build_embedding_function,
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