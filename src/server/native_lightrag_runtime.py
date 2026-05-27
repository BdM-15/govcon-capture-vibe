"""Native LightRAG runtime construction and health reporting."""

from __future__ import annotations

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
    native_pipeline_available_fn: Callable[[], bool] = native_pipeline_available,
    version_resolver: Callable[[str], str] = resolve_package_version,
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
) -> NativeLightRAGRuntime:
    """Build direct LightRAG runtime and initialize native storages."""

    if prompt_map is None:
        from lightrag.prompt import PROMPTS as prompt_map

    if govcon_prompts is None:
        from prompts.govcon_prompt import GOVCON_PROMPTS as govcon_prompts

    prompt_map.update(govcon_prompts)

    if build_runtime_fn is None:
        runtime = build_native_lightrag_runtime(settings, graph_storage=graph_storage)
    else:
        runtime = build_runtime_fn(settings, graph_storage)

    initialize = getattr(runtime.adapter.lightrag, "initialize_storages", None)
    if callable(initialize):
        await initialize()
    return runtime