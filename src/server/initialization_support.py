"""Support helpers for RAG-Anything initialization."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable


@dataclass
class GovconInitializationRuntime:
    """Assembled runtime inputs needed to build and finalize RAGAnything."""

    config: Any
    mineru_output_dir: str
    modal_llm_func: Any
    vision_model_func: Any
    use_strict_schema: bool
    embedding_func: Any
    lightrag_kwargs: dict[str, Any]
    banner_template: str
    chunking_func_name: str


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


def build_govcon_lightrag_setup(
    settings,
    *,
    llm_timeout: int,
    role_llm_configs,
    graph_storage: str | None,
    get_default_catalog: Callable[[], Any] | None = None,
    make_rerank_func: Callable[[], Any] | None = None,
    chunking_func=None,
    banner_template: str | None = None,
) -> dict[str, Any]:
    """Assemble GovCon-specific LightRAG runtime pieces for init."""
    if get_default_catalog is None:
        from src.ontology.entity_catalog import get_default_catalog as _get_default_catalog

        get_default_catalog = _get_default_catalog

    if make_rerank_func is None:
        from src.extraction.govcon_reranker import (
            make_govcon_rerank_func as _make_govcon_rerank_func,
        )

        make_rerank_func = _make_govcon_rerank_func

    if chunking_func is None or banner_template is None:
        from src.extraction.govcon_chunking import (
            BANNER_TEMPLATE as _banner_template,
            govcon_chunking_func as _chunking_func,
        )

        chunking_func = _chunking_func
        banner_template = _banner_template

    entity_types_guidance = get_default_catalog().render_part_d()
    rerank_func = make_rerank_func()
    lightrag_kwargs = {
        "entity_extraction_use_json": True,
        **build_lightrag_runtime_kwargs(
            entity_types_guidance=entity_types_guidance,
            chunking_func=chunking_func,
            llm_timeout=llm_timeout,
            role_llm_configs=role_llm_configs,
            rerank_func=rerank_func,
            min_rerank_score=settings.min_rerank_score,
            graph_storage=graph_storage,
        ),
    }
    return {
        "banner_template": banner_template,
        "chunking_func": chunking_func,
        "chunking_func_name": getattr(chunking_func, "__name__", repr(chunking_func)),
        "entity_types_guidance": entity_types_guidance,
        "rerank_func": rerank_func,
        "lightrag_kwargs": lightrag_kwargs,
    }


def build_raganything_runtime(
    settings,
    *,
    working_dir: str,
    xai_api_key: str,
    xai_base_url: str,
    openai_api_key: str,
    config_cls,
    embed_factory,
    embedding_func_cls,
    graph_storage: str | None,
    configure_mineru_environment_fn=configure_mineru_environment,
    build_raganything_config_fn=build_raganything_config,
    build_role_llm_routing_fn: Callable[..., Any] | None = None,
    build_embedding_function_fn=build_embedding_function,
    build_govcon_lightrag_setup_fn=build_govcon_lightrag_setup,
) -> GovconInitializationRuntime:
    """Assemble config, routing, embedding, runtime kwargs for initialization."""

    if build_role_llm_routing_fn is None:
        from src.server.llm_routing import build_role_llm_routing as _build_role_llm_routing

        build_role_llm_routing_fn = _build_role_llm_routing

    configure_mineru_environment_fn(settings)
    config, mineru_output_dir = build_raganything_config_fn(
        settings,
        working_dir=working_dir,
        config_cls=config_cls,
    )
    role_routing = build_role_llm_routing_fn(
        settings,
        xai_api_key=xai_api_key,
        xai_base_url=xai_base_url,
    )
    embedding_func = build_embedding_function_fn(
        settings,
        openai_api_key=openai_api_key,
        embed_factory=embed_factory,
        embedding_func_cls=embedding_func_cls,
    )
    govcon_runtime = build_govcon_lightrag_setup_fn(
        settings,
        llm_timeout=settings.llm_timeout,
        role_llm_configs=role_routing.role_llm_configs,
        graph_storage=graph_storage,
    )
    return GovconInitializationRuntime(
        config=config,
        mineru_output_dir=mineru_output_dir,
        modal_llm_func=role_routing.modal_llm_func,
        vision_model_func=role_routing.vision_model_func,
        use_strict_schema=role_routing.use_strict_schema,
        embedding_func=embedding_func,
        lightrag_kwargs=govcon_runtime["lightrag_kwargs"],
        banner_template=govcon_runtime["banner_template"],
        chunking_func_name=govcon_runtime["chunking_func_name"],
    )