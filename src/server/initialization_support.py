"""Support helpers for RAG-Anything initialization."""

from __future__ import annotations

import os
from functools import partial
from typing import Any


def configure_mineru_environment(settings, *, environ: dict[str, str] | None = None) -> None:
    """Set MinerU env vars consumed by subprocess/internal config."""
    if environ is None:
        environ = os.environ
    environ["MINERU_DEVICE_MODE"] = settings.mineru_device_mode
    environ["MINERU_TABLE_MERGE_ENABLE"] = (
        "1" if settings.mineru_table_merge_enable else "0"
    )


def build_raganything_config(
    settings,
    *,
    working_dir: str,
    config_cls,
    makedirs=os.makedirs,
) -> tuple[Any, str]:
    """Create RAGAnythingConfig and ensure parser output dir exists."""
    workspace_dir = os.path.join(working_dir, settings.workspace)
    mineru_output_dir = os.path.join(workspace_dir, "mineru")
    makedirs(mineru_output_dir, exist_ok=True)
    config = config_cls(
        working_dir=working_dir,
        parser_output_dir=mineru_output_dir,
        parser=settings.parser,
        parse_method=settings.parse_method,
        enable_image_processing=settings.enable_image_processing,
        enable_table_processing=settings.enable_table_processing,
        enable_equation_processing=settings.enable_equation_processing,
    )
    return config, mineru_output_dir


def build_embedding_function(
    settings,
    *,
    openai_api_key: str,
    embed_factory,
    embedding_func_cls,
):
    """Build EmbeddingFunc using LightRAG native openai_embed implementation."""
    embed_impl = getattr(embed_factory, "func", embed_factory)
    embed_fn = partial(
        embed_impl,
        model=settings.embedding_model,
        api_key=openai_api_key,
        max_token_size=8192,
    )
    return embedding_func_cls(
        embedding_dim=settings.embedding_dim,
        max_token_size=8192,
        func=embed_fn,
    )


def build_lightrag_runtime_kwargs(
    *,
    entity_types_guidance: str,
    chunking_func,
    llm_timeout: int,
    role_llm_configs,
    rerank_func,
    min_rerank_score: float,
    graph_storage: str | None,
) -> dict[str, Any]:
    """Build non-sensitive LightRAG runtime kwargs for initialization."""
    kwargs: dict[str, Any] = {
        "addon_params": {
            "entity_types_guidance": entity_types_guidance,
            "entity_type_prompt_file": "govcon.yaml",
            "language": "English",
        },
        "chunking_func": chunking_func,
        "default_llm_timeout": llm_timeout,
        "role_llm_configs": role_llm_configs,
    }

    if rerank_func is not None:
        kwargs["rerank_model_func"] = rerank_func
        kwargs["min_rerank_score"] = min_rerank_score

    if graph_storage == "Neo4JStorage":
        kwargs["graph_storage"] = graph_storage

    return kwargs