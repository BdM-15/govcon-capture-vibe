"""
RAG-Anything Server with LightRAG WebUI
Multimodal RAG system for government contracting documents

Architecture:
- src/server/config.py: Configuration (ontology-backed entity catalog, API credentials, chunking)
- src/server/initialization.py: RAGAnything initialization (tri-LLM, custom prompts)
- src/server/routes.py: FastAPI endpoints + semantic post-processing
- This file: Main entry point + server orchestration

Workflow:
1. Document Upload → /insert endpoint → UCF detection
2. Dual-Path Processing → Section-aware OR standard extraction
3. Entity Extraction → catalog-driven custom types (extraction LLM: non-reasoning)
4. Semantic Post-Processing → 8 LLM inference algorithms (reasoning LLM)
5. Knowledge Graph Storage → Neo4j or local GraphML
"""

# CRITICAL: Load .env BEFORE any imports that might import LightRAG
# LightRAG's dataclass field defaults evaluate os.getenv() at import time:
#   chunk_token_size: int = field(default=int(os.getenv("CHUNK_SIZE", 1200)))
# If .env isn't loaded first, it uses the hardcoded 1200 default
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from dotenv import load_dotenv
from typing import Any, Callable, Iterator
load_dotenv(override=True)

# Windows MAX_PATH mitigation for MinerU document processing
# MinerU CLI creates mineru-api-client-{random} temp dirs under the system temp
# directory. Long document names (≥60 chars) push the output path:
#   {TEMP}\mineru-api-client-{8}\output\{uuid-36}\{name-69}\auto\{name-69}_origin.pdf
# to ~259 chars — hitting Windows' 260-char MAX_PATH limit and causing
# FileNotFoundError when MinerU tries to write _origin.pdf.
# Fix: redirect Python's tempfile module to a shorter base path.
if sys.platform == "win32":
    import tempfile
    _mineru_temp = os.environ.get("MINERU_TEMP_DIR", r"C:\T")
    os.makedirs(_mineru_temp, exist_ok=True)
    tempfile.tempdir = _mineru_temp

# Now safe to import modules that may import LightRAG
import asyncio
import logging

# Suppress verbose logging from libraries
logging.getLogger("raganything").setLevel(logging.WARNING)
logging.getLogger("lightrag").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Set up logging
logger = logging.getLogger(__name__)


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


async def main():
    """Main server startup with RAG-Anything + LightRAG WebUI
    
    Architecture:
    - RAG-Anything: Document ingestion (MinerU multimodal parser)
    - LightRAG: WebUI + query endpoints (knowledge graph queries)
    - Semantic Post-Processing: Automatic LLM-powered relationship inference
    
    Custom Features:
    - /insert endpoint: Overrides default LightRAG for semantic enhancement
    - Background monitor: Auto-detects WebUI uploads, triggers inference
    - UCF detection: Section-aware extraction for federal RFPs
    """
    from lightrag.api.config import global_args
    from lightrag.api.lightrag_server import create_app
    from src.core import get_settings
    from src.server.config import configure_raganything_args
    from src.server.initialization import initialize_raganything, get_rag_instance
    from src.server.routes import register_custom_ingestion_routes
    from src.server.startup_banner import build_startup_banner_items
    from src.server.ui_query_bridge import make_ui_query_bridges
    from src.server.ui_routes import register_ui
    import uvicorn

    # Initialization message moved to app.py for cleaner startup
    
    # Step 1: Configure LightRAG global_args
    configure_raganything_args()
    
    # Step 2: Initialize RAG-Anything for document processing
    await initialize_raganything()
    rag_instance = get_rag_instance()
    
    if not rag_instance:
        raise RuntimeError("Failed to initialize RAG-Anything instance")
    
    settings = get_settings()
    runtime = build_server_runtime(
        rag_instance,
        settings=settings,
        global_args_obj=global_args,
        logger=logger,
        create_app_fn=create_app,
        register_custom_ingestion_routes_fn=register_custom_ingestion_routes,
        make_ui_query_bridges_fn=make_ui_query_bridges,
        register_ui_fn=register_ui,
        build_startup_banner_items_fn=build_startup_banner_items,
    )

    # Step 5: Start server
    config = uvicorn.Config(app=runtime.app, host=runtime.host, port=runtime.port, log_level="info")
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


if __name__ == "__main__":
    asyncio.run(main())
