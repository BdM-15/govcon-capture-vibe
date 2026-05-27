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
import atexit
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from dotenv import load_dotenv
from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Any, Awaitable, Callable, Iterator
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


KG_MODULES = [
    ("Shipley Methodology", "proposal mechanics · writing craft · color teams"),
    (
        "Evaluation",
        "Evaluation factors / SSEB / source-selection mechanics (UCF Section M or equiv)",
    ),
    ("Regulations", "FAR / DFARS clauses · compliance anchors"),
    ("Workload & Pricing", "BOE · indirect rates · pricing discipline"),
    ("Lessons Learned", "anti-patterns · explicit benefit linkage rule"),
    ("Company Capabilities", "KBR platforms · proof points · past performance"),
]


@dataclass
class ServerRuntime:
    """Built FastAPI app plus resolved host/port."""

    app: Any
    host: str
    port: int


@dataclass
class TheseusRAGRuntime:
    """Native LightRAG runtime plus startup health and settings."""

    adapter: Any
    health: Any
    settings: Any


@dataclass
class UIQueryBridges:
    query: Callable[[str, str, list[dict], bool, dict | None], Awaitable[Any]]
    query_data: Callable[[str, str, list[dict], dict | None], Awaitable[Any]]
    llm: Callable[[str], Awaitable[str]]


def resolve_package_version(pkg: str) -> str:
    try:
        return package_version(pkg)
    except PackageNotFoundError:
        return "unknown"


def format_reranker_line(settings: Any, colors: Any) -> str:
    """Format the reranker status line for the startup banner."""
    if not settings.enable_rerank:
        return f"{colors.DIM}disabled{colors.RESET}"
    rerank_device = settings.rerank_device
    rerank_device_color = colors.GREEN if rerank_device.lower() == "cuda" else colors.YELLOW
    fp_mode = "FP16" if settings.rerank_use_fp16 else "FP32"
    return (
        f"{colors.CYAN}{settings.rerank_model}{colors.RESET}  "
        f"·  Device: {colors.BOLD}{rerank_device_color}{rerank_device.upper()}{colors.RESET}  "
        f"·  {colors.YELLOW}{fp_mode}{colors.RESET}  "
        f"·  Min Score: {colors.DIM}{settings.min_rerank_score}{colors.RESET}"
    )


def build_startup_banner_items(
    settings: Any,
    *,
    host: str,
    port: int,
    graph_storage: str,
    working_dir: str,
    entity_count: int,
    relationship_count: int,
    colors: Any,
    version_resolver: Callable[[str], str] = resolve_package_version,
    pipeline_health: Any | None = None,
) -> list[tuple[str, str]]:
    """Build the startup banner rows for log_banner()."""
    mineru_version = version_resolver("mineru")
    lightrag_version = (
        pipeline_health.lightrag_version
        if pipeline_health is not None
        else version_resolver("lightrag-hku")
    )
    device = settings.mineru_device_mode.upper()
    device_color = colors.GREEN if device == "CUDA" else colors.YELLOW

    startup_items = [
        ("Workspace", f"{colors.BOLD}{colors.WHITE}{settings.workspace}{colors.RESET}"),
        (
            "Storage",
            f"{colors.YELLOW}{graph_storage}{colors.RESET}  ·  {colors.DIM}{working_dir}{colors.RESET}",
        ),
        ("", ""),
        ("Extract  (LightRAG)", f"{colors.CYAN}{settings.extraction_llm_name}{colors.RESET}"),
        ("Keyword  (LightRAG)", f"{colors.CYAN}{settings.keyword_llm_name}{colors.RESET}"),
        ("VLM      (LightRAG)", f"{colors.CYAN}{settings.vlm_llm_name}{colors.RESET}"),
        ("Query    (LightRAG)", f"{colors.MAGENTA}{settings.reasoning_llm_name}{colors.RESET}"),
        ("Post-Process", f"{colors.YELLOW}{settings.post_processing_llm_name}{colors.RESET}"),
        (
            "Embeddings",
            f"{colors.CYAN}{settings.embedding_model}{colors.RESET}  {colors.DIM}({settings.embedding_dim}D){colors.RESET}",
        ),
        ("Reranker", format_reranker_line(settings, colors)),
        ("", ""),
        ("LightRAG", f"{colors.DIM}{lightrag_version}{colors.RESET}"),
        (
            "MinerU",
            f"{colors.DIM}{mineru_version}{colors.RESET}  ·  Device: {colors.BOLD}{device_color}{device}{colors.RESET}  ·  Method: {colors.YELLOW}{settings.parse_method.upper()}{colors.RESET}",
        ),
        ("Multimodal", f"Images · Tables · Equations · Formulas  {colors.GREEN}▸ ENABLED{colors.RESET}"),
        ("", ""),
        (
            "Schema",
            f"{colors.BOLD}{colors.YELLOW}{entity_count}{colors.RESET} entity types  ·  {colors.BOLD}{colors.YELLOW}{relationship_count}{colors.RESET} relationship types",
        ),
        (
            "Inference",
            f"{colors.CYAN}3 LLM algorithms{colors.RESET}  {colors.DIM}(instruction↔evaluation mapping · document structure · orphan resolution){colors.RESET}",
        ),
        ("", ""),
        (
            "Knowledge KG",
            f"{colors.BOLD}{colors.MAGENTA}{len(KG_MODULES)} domain ontologies{colors.RESET}  {colors.DIM}injected for query enrichment{colors.RESET}",
        ),
    ]
    if pipeline_health is None:
        lightrag_index = next(
            index for index, (label, _) in enumerate(startup_items) if label == "LightRAG"
        )
        startup_items.insert(
            lightrag_index + 1,
            ("RAG-Anything", f"{colors.DIM}{version_resolver('raganything')}{colors.RESET}"),
        )
    else:
        pipeline_state = "available" if pipeline_health.native_pipeline_available else "missing"
        storage = pipeline_health.storage
        for index, (label, _) in enumerate(startup_items):
            if label == "Multimodal":
                startup_items[index] = (
                    "Multimodal",
                    f"{pipeline_health.multimodal}  {colors.GREEN}▸ ENABLED{colors.RESET}",
                )
                break
        lightrag_index = next(
            index for index, (label, _) in enumerate(startup_items) if label == "LightRAG"
        )
        startup_items.insert(
            lightrag_index + 1,
            (
                "Native Pipeline",
                f"{colors.GREEN if pipeline_health.native_pipeline_available else colors.YELLOW}{pipeline_state}{colors.RESET}",
            ),
        )
        startup_items.insert(
            lightrag_index + 2,
            ("Role Registry", f"{colors.CYAN}{', '.join(pipeline_health.roles)}{colors.RESET}"),
        )
        startup_items.insert(
            lightrag_index + 3,
            (
                "Storage Detail",
                f"kv={storage['kv']} · vector={storage['vector']} · graph={storage['graph']} · doc_status={storage['doc_status']}",
            ),
        )
    startup_items.extend(
        (f"  {colors.MAGENTA}▸{colors.RESET} {name}", f"{colors.DIM}{description}{colors.RESET}")
        for name, description in KG_MODULES
    )
    startup_items.extend(
        [
            (
                "Scope",
                f"{colors.DIM}Shipley Phase 4-6 — Proposal Planning → Proposal Development → Post-Submittal Activities{colors.RESET}",
            ),
            ("", ""),
            ("WebUI", f"{colors.BLUE}http://{host}:{port}/webui{colors.RESET}"),
            (
                "Capture UI",
                f"{colors.BOLD}{colors.CYAN}http://{host}:{port}/ui{colors.RESET}  {colors.DIM}(new){colors.RESET}",
            ),
            ("API Docs", f"{colors.BLUE}http://{host}:{port}/docs{colors.RESET}"),
        ]
    )
    if graph_storage == "Neo4JStorage":
        startup_items.append(("Neo4j", f"{colors.BLUE}http://localhost:7474{colors.RESET}"))
    return startup_items


async def initialize_theseus_rag_runtime(
    *,
    global_args_obj: Any,
    configure_lightrag_args_fn: Callable[[], None] | None = None,
    initialize_native_lightrag_fn: Callable[..., Awaitable[Any]] | None = None,
    get_settings_fn: Callable[[], Any] | None = None,
) -> TheseusRAGRuntime:
    """Configure and initialize the native LightRAG runtime for Theseus."""

    if configure_lightrag_args_fn is None:
        from src.server.config import configure_lightrag_args as configure_lightrag_args_fn

    if initialize_native_lightrag_fn is None:
        from src.server.native_lightrag_runtime import initialize_native_lightrag as initialize_native_lightrag_fn

    if get_settings_fn is None:
        from src.core import get_settings as get_settings_fn

    configure_lightrag_args_fn()
    settings = get_settings_fn()
    native_runtime = await initialize_native_lightrag_fn(
        settings,
        graph_storage=getattr(global_args_obj, "graph_storage", None),
    )
    return TheseusRAGRuntime(
        adapter=native_runtime.adapter,
        health=native_runtime.health,
        settings=settings,
    )


def make_ui_query_bridges(
    rag_instance: Any,
    *,
    logger: Any,
    query_param_factory: Any | None = None,
) -> UIQueryBridges:
    """Build the UI-facing query/data/LLM bridge callables."""
    if query_param_factory is None:
        from lightrag import QueryParam as query_param_factory

    valid_fields = {f.name for f in query_param_factory.__dataclass_fields__.values()}

    async def _ui_query(
        text: str,
        mode: str,
        history: list[dict],
        stream: bool,
        overrides: dict | None = None,
    ):
        overrides = dict(overrides or {})
        min_score = overrides.pop("min_rerank_score", None)
        if min_score is not None:
            try:
                rag_instance.lightrag.min_rerank_score = float(min_score)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed setting min_rerank_score=%r: %s", min_score, exc)
        param_kwargs = {key: value for key, value in overrides.items() if key in valid_fields}
        return await rag_instance.lightrag.aquery(
            text,
            param=query_param_factory(
                mode=mode,
                stream=stream,
                conversation_history=history or [],
                **param_kwargs,
            ),
        )

    async def _ui_query_data(
        text: str,
        mode: str,
        history: list[dict],
        overrides: dict | None = None,
    ):
        overrides = dict(overrides or {})
        min_score = overrides.pop("min_rerank_score", None)
        if min_score is not None:
            try:
                rag_instance.lightrag.min_rerank_score = float(min_score)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed setting min_rerank_score=%r: %s", min_score, exc)
        param_kwargs = {key: value for key, value in overrides.items() if key in valid_fields}
        param_kwargs.pop("stream", None)
        return await rag_instance.lightrag.aquery_data(
            text,
            param=query_param_factory(
                mode=mode,
                conversation_history=history or [],
                **param_kwargs,
            ),
        )

    async def _ui_llm(prompt: str) -> str:
        llm = getattr(rag_instance.lightrag, "llm_model_func", None)
        if llm is None:
            raise RuntimeError("LightRAG instance has no llm_model_func configured")
        result = await llm(prompt, system_prompt=None, history_messages=[])
        return result if isinstance(result, str) else str(result)

    return UIQueryBridges(query=_ui_query, query_data=_ui_query_data, llm=_ui_llm)


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
    pipeline_health: Any | None = None,
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
        pipeline_health=pipeline_health,
    )
    log_banner_fn(
        f"{colors.BOLD}✅ PROJECT THESEUS — READY{colors.RESET}",
        items=startup_items,
        logger=logger,
        force_print=True,
    )

    return ServerRuntime(app=app, host=host, port=port)


def unregister_raganything_atexit(rag_instance: Any, *, logger: Any) -> bool:
    close_callback = getattr(rag_instance, "close", None)
    if close_callback is None:
        return False

    try:
        atexit.unregister(close_callback)
    except ValueError:
        return False
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed unregistering RAG-Anything atexit cleanup: %s", exc)
        return False
    return True


async def finalize_raganything_for_shutdown(rag_instance: Any, *, logger: Any) -> None:
    if rag_instance is None:
        return

    if getattr(rag_instance, "_theseus_shutdown_finalized", False):
        return

    setattr(rag_instance, "_theseus_shutdown_finalized", True)
    finalize = getattr(rag_instance, "finalize_storages", None)
    if finalize is None:
        unregister_raganything_atexit(rag_instance, logger=logger)
        return

    try:
        await finalize()
    except Exception:  # noqa: BLE001
        logger.exception("RAG-Anything shutdown finalization failed")
    finally:
        unregister_raganything_atexit(rag_instance, logger=logger)


async def serve_with_rag_shutdown(
    server_instance: Any,
    rag_instance: Any,
    *,
    logger: Any,
) -> None:
    try:
        await server_instance.serve()
    finally:
        await finalize_raganything_for_shutdown(rag_instance, logger=logger)


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
    from src.server.routes import register_custom_ingestion_routes
    from src.server.ui_routes import register_ui
    import uvicorn

    # Initialization message moved to app.py for cleaner startup

    rag_runtime = await initialize_theseus_rag_runtime(global_args_obj=global_args)
    rag_instance = rag_runtime.adapter
    runtime = build_server_runtime(
        rag_instance,
        settings=rag_runtime.settings,
        global_args_obj=global_args,
        logger=logger,
        create_app_fn=create_app,
        register_custom_ingestion_routes_fn=register_custom_ingestion_routes,
        make_ui_query_bridges_fn=make_ui_query_bridges,
        register_ui_fn=register_ui,
        build_startup_banner_items_fn=build_startup_banner_items,
        pipeline_health=rag_runtime.health,
    )

    # Step 5: Start server
    config = uvicorn.Config(app=runtime.app, host=runtime.host, port=runtime.port, log_level="info")
    server_instance = uvicorn.Server(config)
    await serve_with_rag_shutdown(server_instance, rag_instance, logger=logger)


if __name__ == "__main__":
    asyncio.run(main())
