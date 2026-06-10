"""
LightRAG-first Capture Workbench server.
Multimodal RAG system for government contracting documents.

Architecture:
- src/server/config.py: Configuration (ontology-backed entity catalog, API credentials, chunking)
- src/server/native_lightrag_runtime.py: Native LightRAG runtime, role routing, parser health
- src/server/routes.py: FastAPI endpoints + semantic post-processing
- This file: Main entry point + server orchestration

Workflow:
1. Document Upload → /insert or /documents/upload
2. Native LightRAG parser routing → MinerU/native parser + multimodal analysis
3. Entity Extraction → catalog-driven custom types (extraction LLM: non-reasoning)
4. Semantic Post-Processing → L↔M, document structure, orphan resolution
5. Knowledge Graph Storage → Neo4j or local GraphML
"""

# CRITICAL: Load .env BEFORE any imports that might import LightRAG
# LightRAG's dataclass field defaults evaluate os.getenv() at import time:
#   chunk_token_size: int = field(default=int(os.getenv("CHUNK_SIZE", 1200)))
# If .env isn't loaded first, it uses the hardcoded 1200 default
import contextvars
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
logging.getLogger("lightrag").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Set up logging
logger = logging.getLogger("theseus.server")


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
    ollama_status: dict[str, Any] | None = None


@dataclass
class UIQueryBridges:
    query: Callable[[str, str, list[dict], bool, dict | None], Awaitable[Any]]
    query_data: Callable[[str, str, list[dict], dict | None], Awaitable[Any]]
    query_llm: Callable[[str, str, list[dict], bool, dict | None], Awaitable[Any]]
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
    ollama_status: dict[str, Any] | None = None,
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

    from src.server.ollama_llm import format_ollama_banner_line

    startup_items = [
        ("Workspace", f"{colors.BOLD}{colors.WHITE}{settings.workspace}{colors.RESET}"),
        (
            "Storage",
            f"{colors.YELLOW}{graph_storage}{colors.RESET}  ·  {colors.DIM}{working_dir}{colors.RESET}",
        ),
        (
            "Runtime",
            f"{colors.GREEN}LightRAG-first Capture Workbench{colors.RESET}  ·  {colors.DIM}native ingestion + native multimodal{colors.RESET}",
        ),
        ("", ""),
        ("Extract  (LightRAG)", f"{colors.CYAN}{settings.extraction_llm_name}{colors.RESET}"),
        (
            "Keyword  (LightRAG)",
            (
                f"{colors.CYAN}{settings.keyword_llm_name}{colors.RESET}"
                + (
                    f"  {colors.DIM}·  ollama @ {getattr(settings, 'ollama_host', 'http://localhost:11434')}{colors.RESET}"
                    if getattr(settings, "keyword_uses_ollama", False)
                    else ""
                )
            ),
        ),
        ("Ollama   (local)", format_ollama_banner_line(ollama_status, settings, colors)),
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
    if pipeline_health is not None:
        pipeline_state = "available" if pipeline_health.native_pipeline_available else "missing"
        storage = pipeline_health.storage
        parser = pipeline_health.parser
        for index, (label, _) in enumerate(startup_items):
            if label == "Multimodal":
                startup_items[index] = (
                    "Multimodal",
                    f"{pipeline_health.multimodal}  {colors.GREEN}▸ ENABLED{colors.RESET}",
                )
            if label == "MinerU":
                startup_items[index] = (
                    "MinerU",
                    f"{colors.DIM}{mineru_version}{colors.RESET}  ·  Mode: {colors.YELLOW}{parser.mineru_api_mode.upper()}{colors.RESET}  ·  Backend: {colors.CYAN}{parser.mineru_backend}{colors.RESET}  ·  Method: {colors.YELLOW}{parser.mineru_parse_method}{colors.RESET}",
                )
            if label == "MinerU" and parser.mineru_endpoint:
                startup_items[index] = (
                    "MinerU",
                    f"{startup_items[index][1]}  ·  Endpoint: {colors.DIM}{parser.mineru_endpoint}{colors.RESET}",
                )
            if label == "Multimodal":
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
        startup_items.insert(
            lightrag_index + 4,
            ("Parser Routing", f"{colors.CYAN}{parser.routing or 'legacy'}{colors.RESET}"),
        )
        startup_items.insert(
            lightrag_index + 5,
            (
                "MinerU Mode",
                f"{colors.YELLOW}{parser.mineru_api_mode}{colors.RESET} · backend={parser.mineru_backend} · method={parser.mineru_parse_method}",
            ),
        )
        startup_items.insert(
            lightrag_index + 6,
            (
                "Parser Workers",
                f"native={parser.concurrency['native']} · mineru={parser.concurrency['mineru']} · docling={parser.concurrency['docling']} · analyze={parser.concurrency['analyze']}",
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
                "Capture Workbench",
                f"{colors.BOLD}{colors.CYAN}http://{host}:{port}/ui{colors.RESET}  {colors.DIM}(new){colors.RESET}",
            ),
            ("API Docs", f"{colors.BLUE}http://{host}:{port}/docs{colors.RESET}"),
        ]
    )
    if graph_storage == "Neo4JStorage":
        startup_items.append(("Neo4j", f"{colors.BLUE}http://localhost:7474{colors.RESET}"))
    return startup_items


async def maybe_bootstrap_govcon_ontology(
    *,
    lightrag: Any,
    settings: Any,
    bootstrap_fn: Callable[..., Awaitable[dict]] | None = None,
    log: Any = logger,
) -> dict | None:
    """Inject the curated GovCon domain ontology into the active workspace once.

    Restored after the RAG-Anything removal epic dropped the prior caller in
    ``src/server/rag_post_init.py``. Honors ``AUTO_BOOTSTRAP_ONTOLOGY`` and
    ``ONTOLOGY_BOOTSTRAP_FORCE`` from settings, no-ops on subsequent runs via
    the workspace's ``.ontology_bootstrap`` marker, and never blocks startup
    if bootstrap fails.
    """

    if not getattr(settings, "auto_bootstrap_ontology", True):
        log.info("📚 Ontology auto-bootstrap DISABLED (AUTO_BOOTSTRAP_ONTOLOGY=False)")
        return None

    if bootstrap_fn is None:
        from src.ontology.bootstrap import bootstrap_govcon_ontology as bootstrap_fn

    workspace_path = os.path.join(settings.working_dir, settings.workspace)
    try:
        result = await bootstrap_fn(
            lightrag=lightrag,
            working_dir=workspace_path,
            force=getattr(settings, "ontology_bootstrap_force", False),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "⚠️ Ontology bootstrap failed: %s — continuing without domain knowledge",
            exc,
        )
        return None

    status = result.get("status")
    if status == "success":
        log.info(
            "✅ GovCon ontology bootstrapped into workspace '%s': %s entities, %s relationships",
            settings.workspace,
            result.get("entities_added"),
            result.get("relationships_added"),
        )
    elif status == "already_bootstrapped":
        log.info(
            "📚 GovCon ontology already bootstrapped into workspace '%s' (%s)",
            settings.workspace,
            result.get("bootstrapped_at"),
        )
    else:
        log.warning("⚠️ Ontology bootstrap: %s", result.get("error", "unknown issue"))
    return result


async def initialize_theseus_rag_runtime(
    *,
    global_args_obj: Any,
    configure_lightrag_args_fn: Callable[[], None] | None = None,
    initialize_native_lightrag_fn: Callable[..., Awaitable[Any]] | None = None,
    get_settings_fn: Callable[[], Any] | None = None,
    set_active_rag_instance_fn: Callable[[Any], None] | None = None,
    bootstrap_ontology_fn: Callable[..., Awaitable[Any]] | None = None,
) -> TheseusRAGRuntime:
    """Configure and initialize the native LightRAG runtime for Theseus."""

    if configure_lightrag_args_fn is None:
        from src.server.config import configure_lightrag_args as configure_lightrag_args_fn

    if initialize_native_lightrag_fn is None:
        from src.server.native_lightrag_runtime import initialize_native_lightrag as initialize_native_lightrag_fn

    if get_settings_fn is None:
        from src.core import get_settings as get_settings_fn

    if set_active_rag_instance_fn is None:
        from src.server.runtime_state import set_active_rag_instance as set_active_rag_instance_fn

    if bootstrap_ontology_fn is None:
        bootstrap_ontology_fn = maybe_bootstrap_govcon_ontology

    configure_lightrag_args_fn()
    settings = get_settings_fn()
    from src.server.ollama_llm import log_ollama_startup, warmup_ollama
    from src.server.runtime_state import get_ollama_status, set_ollama_status

    ollama_status = get_ollama_status()
    if not ollama_status or not ollama_status.get("ok"):
        try:
            ollama_status = await warmup_ollama(settings)
            set_ollama_status(ollama_status)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama async warmup failed: %s", exc)
            ollama_status = ollama_status or {"ok": False, "state": "unavailable", "error": str(exc)[:160]}
            set_ollama_status(ollama_status)
    log_ollama_startup(ollama_status, logger_obj=logger)

    native_runtime = await initialize_native_lightrag_fn(
        settings,
        graph_storage=getattr(global_args_obj, "graph_storage", None),
    )
    set_active_rag_instance_fn(native_runtime.adapter)
    await bootstrap_ontology_fn(
        lightrag=getattr(native_runtime.adapter, "lightrag", None),
        settings=settings,
    )
    return TheseusRAGRuntime(
        adapter=native_runtime.adapter,
        health=native_runtime.health,
        settings=settings,
        ollama_status=ollama_status,
    )


def _prepare_ui_query_overrides(
    rag_instance: Any,
    overrides: dict | None,
    *,
    logger: Any,
    valid_fields: set[str],
) -> tuple[dict[str, Any], contextvars.Token[float | None] | None]:
    """Apply per-query UI tunables to LightRAG and the govcon reranker."""
    from src.extraction.govcon_reranker import set_active_min_rerank_score

    overrides = dict(overrides or {})
    rerank_token: contextvars.Token[float | None] | None = None
    min_score = overrides.pop("min_rerank_score", None)
    if min_score is not None:
        try:
            score = float(min_score)
            rag_instance.lightrag.min_rerank_score = score
            rerank_token = set_active_min_rerank_score(score)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed setting min_rerank_score=%r: %s", min_score, exc)

    param_kwargs = {key: value for key, value in overrides.items() if key in valid_fields}
    from src.server.chat_routes import DEFAULT_RESPONSE_TYPE

    param_kwargs.setdefault("response_type", DEFAULT_RESPONSE_TYPE)
    if param_kwargs or min_score is not None:
        logger.info(
            "Query tunables: %s",
            {
                **param_kwargs,
                **(
                    {"min_rerank_score": float(min_score)}
                    if min_score is not None
                    else {}
                ),
            },
        )
    return param_kwargs, rerank_token


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
        from src.extraction.govcon_reranker import reset_active_min_rerank_score

        param_kwargs, rerank_token = _prepare_ui_query_overrides(
            rag_instance,
            overrides,
            logger=logger,
            valid_fields=valid_fields,
        )
        try:
            return await rag_instance.lightrag.aquery(
                text,
                param=query_param_factory(
                    mode=mode,
                    stream=stream,
                    conversation_history=history or [],
                    **param_kwargs,
                ),
            )
        finally:
            if rerank_token is not None:
                reset_active_min_rerank_score(rerank_token)

    async def _ui_query_data(
        text: str,
        mode: str,
        history: list[dict],
        overrides: dict | None = None,
    ):
        from src.extraction.govcon_reranker import reset_active_min_rerank_score

        param_kwargs, rerank_token = _prepare_ui_query_overrides(
            rag_instance,
            overrides,
            logger=logger,
            valid_fields=valid_fields,
        )
        param_kwargs.pop("stream", None)
        try:
            return await rag_instance.lightrag.aquery_data(
                text,
                param=query_param_factory(
                    mode=mode,
                    conversation_history=history or [],
                    **param_kwargs,
                ),
            )
        finally:
            if rerank_token is not None:
                reset_active_min_rerank_score(rerank_token)

    async def _ui_query_llm(
        text: str,
        mode: str,
        history: list[dict],
        stream: bool,
        overrides: dict | None = None,
    ):
        from src.extraction.govcon_reranker import reset_active_min_rerank_score

        param_kwargs, rerank_token = _prepare_ui_query_overrides(
            rag_instance,
            overrides,
            logger=logger,
            valid_fields=valid_fields,
        )
        try:
            return await rag_instance.lightrag.aquery_llm(
                text,
                param=query_param_factory(
                    mode=mode,
                    stream=stream,
                    conversation_history=history or [],
                    **param_kwargs,
                ),
            )
        finally:
            if rerank_token is not None:
                reset_active_min_rerank_score(rerank_token)

    async def _ui_llm(prompt: str) -> str:
        llm = getattr(rag_instance.lightrag, "llm_model_func", None)
        if llm is None:
            raise RuntimeError("LightRAG instance has no llm_model_func configured")
        result = await llm(prompt, system_prompt=None, history_messages=[])
        return result if isinstance(result, str) else str(result)

    return UIQueryBridges(
        query=_ui_query,
        query_data=_ui_query_data,
        query_llm=_ui_query_llm,
        llm=_ui_llm,
    )


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
    ollama_status: dict[str, Any] | None = None,
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
    register_ui_fn(
        app,
        ui_bridges.query,
        ui_bridges.query_data,
        query_llm_func=ui_bridges.query_llm,
        llm_func=ui_bridges.llm,
    )

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
        ollama_status=ollama_status,
    )
    log_banner_fn(
        f"{colors.BOLD}✅ LIGHTRAG-FIRST CAPTURE WORKBENCH READY{colors.RESET}",
        items=startup_items,
        logger=logger,
        force_print=True,
    )

    return ServerRuntime(app=app, host=host, port=port)


async def finalize_native_runtime_for_shutdown(rag_instance: Any, *, logger: Any) -> None:
    if rag_instance is None:
        return

    if getattr(rag_instance, "_theseus_shutdown_finalized", False):
        return

    setattr(rag_instance, "_theseus_shutdown_finalized", True)
    finalize = getattr(rag_instance, "finalize_storages", None)
    if finalize is None:
        return

    try:
        await finalize()
    except Exception:  # noqa: BLE001
        logger.exception("Native runtime shutdown finalization failed")


async def serve_with_runtime_shutdown(
    server_instance: Any,
    rag_instance: Any,
    *,
    logger: Any,
) -> None:
    try:
        await server_instance.serve()
    finally:
        await finalize_native_runtime_for_shutdown(rag_instance, logger=logger)


async def main():
    """Main server startup with native LightRAG + Theseus UI
    
    Architecture:
    - LightRAG: Native parser pipeline, WebUI, and query endpoints
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
        ollama_status=rag_runtime.ollama_status,
    )

    # Step 5: Start server
    config = uvicorn.Config(app=runtime.app, host=runtime.host, port=runtime.port, log_level="info")
    server_instance = uvicorn.Server(config)
    await serve_with_runtime_shutdown(server_instance, rag_instance, logger=logger)


if __name__ == "__main__":
    asyncio.run(main())
