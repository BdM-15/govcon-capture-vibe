"""Native LightRAG runtime construction and health reporting."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import partial
from importlib import metadata, util
from typing import Any, Callable


LOCAL_KV_STORAGE = "JsonKVStorage"
LOCAL_VECTOR_STORAGE = "NanoVectorDBStorage"
LOCAL_DOC_STATUS_STORAGE = "JsonDocStatusStorage"


@dataclass(frozen=True)
class NativePipelineHealth:
    """Operator-visible summary of the active native LightRAG runtime."""

    lightrag_version: str
    native_pipeline_available: bool
    roles: list[str]
    storage: dict[str, str]
    multimodal: str
    parser: NativeParserHealth


@dataclass(frozen=True)
class NativeParserHealth:
    """Resolved LightRAG-native parser routing and MinerU mode."""

    routing: str
    mineru_api_mode: str
    mineru_endpoint: str
    mineru_backend: str
    mineru_parse_method: str
    concurrency: dict[str, int]


@dataclass
class NativeLightRAGAdapter:
    """Thin compatibility shell for server code that expects `.lightrag`."""

    lightrag: Any
    llm_model_func: Any
    vision_model_func: Any

    async def finalize_storages(self) -> None:
        finalize = getattr(self.lightrag, "finalize_storages", None)
        if callable(finalize):
            await finalize()


@dataclass(frozen=True)
class NativeLightRAGRuntime:
    adapter: NativeLightRAGAdapter
    health: NativePipelineHealth


def resolve_package_version(pkg: str) -> str:
    try:
        return metadata.version(pkg)
    except metadata.PackageNotFoundError:
        return "unknown"


def native_pipeline_available() -> bool:
    return util.find_spec("lightrag.pipeline") is not None


def _env_bool(value: Any) -> str:
    return "true" if bool(value) else "false"


def configure_native_parser_environment(
    settings: Any,
    *,
    environ: dict[str, str] | None = None,
    validate_parser_routing_fn: Callable[[str], None] | None = None,
) -> NativeParserHealth:
    """Configure LightRAG-native parser routing env consumed by rc3 pipeline."""

    if environ is None:
        environ = os.environ

    if validate_parser_routing_fn is None:
        from lightrag.parser.routing import validate_parser_routing_config as validate_parser_routing_fn

    routing = str(getattr(settings, "lightrag_parser", "") or "").strip()
    mineru_api_mode = str(getattr(settings, "mineru_api_mode", "local") or "local").strip().lower()
    mineru_local_endpoint = str(getattr(settings, "mineru_local_endpoint", "") or "").strip()
    mineru_official_endpoint = str(
        getattr(settings, "mineru_official_endpoint", "https://mineru.net") or "https://mineru.net"
    ).strip()
    mineru_endpoint = mineru_official_endpoint if mineru_api_mode == "official" else mineru_local_endpoint
    mineru_backend = str(getattr(settings, "mineru_local_backend", "pipeline") or "pipeline").strip()
    mineru_parse_method = str(
        getattr(settings, "mineru_local_parse_method", "auto") or "auto"
    ).strip()
    concurrency = {
        "native": int(getattr(settings, "max_parallel_parse_native", 5)),
        "mineru": int(getattr(settings, "max_parallel_parse_mineru", 1)),
        "docling": int(getattr(settings, "max_parallel_parse_docling", 1)),
        "analyze": int(getattr(settings, "max_parallel_analyze", 5)),
    }
    image_processing = bool(getattr(settings, "enable_image_processing", True))
    table_processing = bool(getattr(settings, "enable_table_processing", True))
    equation_processing = bool(getattr(settings, "enable_equation_processing", True))
    vlm_process_enable = bool(
        getattr(
            settings,
            "vlm_process_enable",
            image_processing or table_processing or equation_processing,
        )
    )

    environ["LIGHTRAG_PARSER"] = routing
    environ["MINERU_API_MODE"] = mineru_api_mode
    environ["MINERU_LOCAL_ENDPOINT"] = mineru_local_endpoint
    environ["MINERU_OFFICIAL_ENDPOINT"] = mineru_official_endpoint
    mineru_api_token = getattr(settings, "mineru_api_token", None)
    if mineru_api_token:
        environ["MINERU_API_TOKEN"] = str(mineru_api_token)
    environ["MINERU_LOCAL_BACKEND"] = mineru_backend
    environ["MINERU_LOCAL_PARSE_METHOD"] = mineru_parse_method
    environ["MINERU_LANGUAGE"] = str(getattr(settings, "mineru_language", "en") or "en").strip()
    environ["MINERU_ENABLE_TABLE"] = _env_bool(table_processing)
    environ["MINERU_ENABLE_FORMULA"] = _env_bool(equation_processing)
    environ["MINERU_LOCAL_IMAGE_ANALYSIS"] = _env_bool(image_processing)
    environ["VLM_PROCESS_ENABLE"] = _env_bool(vlm_process_enable)
    environ["MAX_PARALLEL_PARSE_NATIVE"] = str(concurrency["native"])
    environ["MAX_PARALLEL_PARSE_MINERU"] = str(concurrency["mineru"])
    environ["MAX_PARALLEL_PARSE_DOCLING"] = str(concurrency["docling"])
    environ["MAX_PARALLEL_ANALYZE"] = str(concurrency["analyze"])

    validate_parser_routing_fn(routing)
    return NativeParserHealth(
        routing=routing,
        mineru_api_mode=mineru_api_mode,
        mineru_endpoint=mineru_endpoint,
        mineru_backend=mineru_backend,
        mineru_parse_method=mineru_parse_method,
        concurrency=concurrency,
    )


def build_native_lightrag_runtime(
    settings: Any,
    *,
    graph_storage: str | None,
    lightrag_cls: Callable[..., Any] | None = None,
    embed_factory: Any | None = None,
    embedding_func_cls: Callable[..., Any] | None = None,
    build_role_llm_routing_fn: Callable[..., Any] | None = None,
    get_default_catalog: Callable[[], Any] | None = None,
    make_rerank_func: Callable[[], Any] | None = None,
    chunking_func: Callable[..., Any] | None = None,
    configure_native_parser_environment_fn: Callable[[Any], NativeParserHealth] = configure_native_parser_environment,
    native_pipeline_available_fn: Callable[[], bool] = native_pipeline_available,
    version_resolver: Callable[[str], str] = resolve_package_version,
    install_chunk_guardrails_fn: Callable[[], None] | None = None,
) -> NativeLightRAGRuntime:
    """Construct direct LightRAG runtime plus health data for startup surfaces."""

    if lightrag_cls is None:
        from lightrag import LightRAG as lightrag_cls

    if embed_factory is None:
        from lightrag.llm.openai import openai_embed as embed_factory

    if embedding_func_cls is None:
        from lightrag.utils import EmbeddingFunc as embedding_func_cls

    if build_role_llm_routing_fn is None:
        from src.server.llm_routing import build_role_llm_routing as build_role_llm_routing_fn

    if get_default_catalog is None:
        from src.ontology.entity_catalog import get_default_catalog as get_default_catalog

    if make_rerank_func is None:
        from src.extraction.govcon_reranker import make_govcon_rerank_func as make_rerank_func

    if chunking_func is None:
        from src.extraction.govcon_chunking import govcon_chunking_func as chunking_func

    if install_chunk_guardrails_fn is None:
        from src.extraction.govcon_chunking import (
            install_govcon_native_chunk_guardrails as install_chunk_guardrails_fn,
        )

    install_chunk_guardrails_fn()

    parser_health = configure_native_parser_environment_fn(settings)
    role_routing = build_role_llm_routing_fn(
        settings,
        xai_api_key=settings.llm_binding_api_key,
        xai_base_url=settings.llm_binding_host,
    )
    embed_impl = getattr(embed_factory, "func", embed_factory)
    embed_fn = partial(
        embed_impl,
        model=settings.embedding_model,
        api_key=settings.embedding_binding_api_key,
        max_token_size=8192,
    )
    embedding_func = embedding_func_cls(
        embedding_dim=settings.embedding_dim,
        max_token_size=8192,
        func=embed_fn,
    )

    entity_types_guidance = get_default_catalog().render_part_d()
    effective_graph_storage = graph_storage or "NetworkXStorage"
    storage = {
        "kv": LOCAL_KV_STORAGE,
        "vector": LOCAL_VECTOR_STORAGE,
        "graph": effective_graph_storage,
        "doc_status": LOCAL_DOC_STATUS_STORAGE,
    }
    lightrag_kwargs: dict[str, Any] = {
        "working_dir": settings.working_dir,
        "workspace": settings.workspace,
        "kv_storage": LOCAL_KV_STORAGE,
        "vector_storage": LOCAL_VECTOR_STORAGE,
        "doc_status_storage": LOCAL_DOC_STATUS_STORAGE,
        "graph_storage": effective_graph_storage,
        "llm_model_func": role_routing.modal_llm_func,
        "embedding_func": embedding_func,
        "entity_extraction_use_json": True,
        "addon_params": {
            "entity_types_guidance": entity_types_guidance,
            "entity_type_prompt_file": "govcon.yaml",
            "language": "English",
        },
        "chunking_func": chunking_func,
        "default_llm_timeout": settings.llm_timeout,
        "role_llm_configs": role_routing.role_llm_configs,
        "vlm_process_enable": bool(getattr(settings, "vlm_process_enable", True)),
        "max_parallel_parse_native": parser_health.concurrency["native"],
        "max_parallel_parse_mineru": parser_health.concurrency["mineru"],
        "max_parallel_parse_docling": parser_health.concurrency["docling"],
        "max_parallel_analyze": parser_health.concurrency["analyze"],
    }

    rerank_func = make_rerank_func()
    if rerank_func is not None:
        lightrag_kwargs["rerank_model_func"] = rerank_func
        lightrag_kwargs["min_rerank_score"] = settings.min_rerank_score

    lightrag = lightrag_cls(**lightrag_kwargs)
    native_available = native_pipeline_available_fn()
    health = NativePipelineHealth(
        lightrag_version=version_resolver("lightrag-hku"),
        native_pipeline_available=native_available,
        roles=sorted(role_routing.role_llm_configs.keys()),
        storage=storage,
        multimodal="native" if native_available else "unavailable",
        parser=parser_health,
    )
    return NativeLightRAGRuntime(
        adapter=NativeLightRAGAdapter(
            lightrag=lightrag,
            llm_model_func=role_routing.modal_llm_func,
            vision_model_func=role_routing.vision_model_func,
        ),
        health=health,
    )


async def initialize_native_lightrag(
    settings: Any,
    *,
    graph_storage: str | None,
    build_runtime_fn: Callable[[Any, str | None], NativeLightRAGRuntime] | None = None,
    prompt_map: dict[str, Any] | None = None,
    govcon_prompts: dict[str, Any] | None = None,
    multimodal_prompt_map: dict[str, Any] | None = None,
    native_multimodal_prompts: dict[str, Any] | None = None,
) -> NativeLightRAGRuntime:
    """Build direct LightRAG runtime and initialize native storages."""

    if prompt_map is None:
        from lightrag.prompt import PROMPTS as prompt_map

    if govcon_prompts is None:
        from prompts.govcon_prompt import GOVCON_PROMPTS as govcon_prompts

    if multimodal_prompt_map is None:
        from lightrag.prompt_multimodal import MULTIMODAL_PROMPTS as multimodal_prompt_map

    if native_multimodal_prompts is None:
        from prompts.multimodal.govcon_multimodal_prompts import (
            GOVCON_NATIVE_MULTIMODAL_PROMPTS as native_multimodal_prompts,
        )

    prompt_map.update(govcon_prompts)
    multimodal_prompt_map.update(native_multimodal_prompts)

    if build_runtime_fn is None:
        runtime = build_native_lightrag_runtime(settings, graph_storage=graph_storage)
    else:
        runtime = build_runtime_fn(settings, graph_storage)

    initialize = getattr(runtime.adapter.lightrag, "initialize_storages", None)
    if callable(initialize):
        await initialize()
    return runtime