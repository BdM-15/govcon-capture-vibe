"""App assembly + API-server patching for the Theseus runtime."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator


@dataclass
class ServerRuntime:
    """Built FastAPI app plus resolved host/port."""

    app: Any
    host: str
    port: int


@contextmanager
def patch_api_server_lightrag_for_local_rerank(
    *,
    local_rerank: Any,
    logger: Any,
    api_module: Any | None = None,
) -> Iterator[None]:
    """Temporarily patch API-server LightRAG to inject local rerank support."""

    if local_rerank is None:
        yield
        return

    if api_module is None:
        import lightrag.api.lightrag_server as api_module

    original_lightrag = api_module.LightRAG

    class _LightRAGWithLocalRerank(original_lightrag):
        def __init__(self, *args, **kwargs):
            if kwargs.get("rerank_model_func") is None:
                kwargs["rerank_model_func"] = local_rerank
                logger.info(
                    "🎯 Auto-injecting local BGE reranker into API server's "
                    "LightRAG (workspace=%s)",
                    kwargs.get("workspace", "?"),
                )
            kwargs.setdefault("entity_extraction_use_json", True)
            super().__init__(*args, **kwargs)

    api_module.LightRAG = _LightRAGWithLocalRerank
    try:
        yield
    finally:
        api_module.LightRAG = original_lightrag


def build_server_runtime(
    rag_instance: Any,
    *,
    settings: Any,
    global_args_obj: Any,
    logger: Any,
    create_app_fn: Callable[[Any], Any],
    register_custom_ingestion_routes_fn: Callable[..., None],
    make_ui_query_bridges_fn: Callable[..., Any],
    register_ui_fn: Callable[..., None],
    build_startup_banner_items_fn: Callable[..., list[tuple[str, str]]],
    make_rerank_func: Callable[[], Any] | None = None,
    log_banner_fn: Callable[..., None] | None = None,
    colors: Any | None = None,
    entity_types: list[Any] | None = None,
    relationship_types: list[Any] | None = None,
) -> ServerRuntime:
    """Build app, wire routes/UI, log banner, return launch config."""

    if make_rerank_func is None:
        from src.extraction.govcon_reranker import make_govcon_rerank_func as _make_rerank

        make_rerank_func = _make_rerank

    if log_banner_fn is None or colors is None:
        from src.utils.logging_config import Colors, log_banner

        colors = Colors
        log_banner_fn = log_banner

    if entity_types is None or relationship_types is None:
        from src.ontology.schema import VALID_ENTITY_TYPES, VALID_RELATIONSHIP_TYPES

        entity_types = VALID_ENTITY_TYPES
        relationship_types = VALID_RELATIONSHIP_TYPES

    host = global_args_obj.host
    port = global_args_obj.port
    local_rerank = make_rerank_func()

    with patch_api_server_lightrag_for_local_rerank(
        local_rerank=local_rerank,
        logger=logger,
    ):
        app = create_app_fn(global_args_obj)

    register_custom_ingestion_routes_fn(app, rag_instance, logger=logger)

    ui_bridges = make_ui_query_bridges_fn(rag_instance, logger=logger)
    register_ui_fn(app, ui_bridges.query, ui_bridges.query_data, llm_func=ui_bridges.llm)

    graph_storage = (
        global_args_obj.graph_storage
        if hasattr(global_args_obj, "graph_storage")
        else "NetworkXStorage"
    )
    startup_items = build_startup_banner_items_fn(
        settings,
        host=host,
        port=port,
        graph_storage=graph_storage,
        working_dir=global_args_obj.working_dir,
        entity_count=len(entity_types),
        relationship_count=len(relationship_types),
        colors=colors,
    )
    log_banner_fn(
        f"{colors.BOLD}✅ PROJECT THESEUS — READY{colors.RESET}",
        items=startup_items,
        logger=logger,
        force_print=True,
    )

    return ServerRuntime(app=app, host=host, port=port)