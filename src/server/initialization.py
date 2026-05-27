"""
Legacy compatibility initialization module.

This module handles the temporary RAG-Anything compatibility instance with:
- Custom entity extraction prompts (govcon_lightrag_json.txt, Parts A-L)
- Government contracting ontology (catalog-driven entity types, canonical relationship set)
- Multimodal document processing (MinerU parser)
- Cloud LLM integration (xAI Grok extraction + fast-reasoning post-processing + grok-4.20 queries + OpenAI embeddings)
"""

# CRITICAL: Ensure .env is loaded before LightRAG imports
# This file is imported by raganything_server.py which loads .env first
# But we import it here too for safety if this module is used standalone
import os
from dataclasses import dataclass
from dotenv import load_dotenv
from functools import partial
from typing import Any, Callable
load_dotenv(override=True)

# Apply compatibility patches BEFORE raganything imports
from tools.patches.raganything_libreoffice_windows import apply_patch as _apply_lo_patch
_apply_lo_patch()
from tools.patches.raganything_mineru_error_details import apply_patch as _apply_mineru_error_patch
_apply_mineru_error_patch()

# Now safe to import LightRAG and related modules
import logging
from lightrag.api.config import global_args
from lightrag.lightrag import RoleLLMConfig
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc
from raganything import RAGAnything, RAGAnythingConfig

# V3 unified prompt loaded directly from file - no prompt_loader needed
from src.ontology.schema import VALID_ENTITY_TYPES
from src.core import get_settings
from src.server.rag_post_init import finalize_rag_initialization
from src.utils.time_utils import to_local_iso

logger = logging.getLogger(__name__)

# Global compatibility instance
_rag_anything = None


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


async def initialize_raganything():
    """Initialize the legacy compatibility instance.
    
    Configuration:
    - Parser: MinerU (multimodal - images, tables, equations)
    - Entity Types: ontology-driven government contracting types
    - Extraction LLM: xAI Grok-4-fast-non-reasoning (literal format compliance)
    - Reasoning LLM: xAI grok-4.20-0309-reasoning (queries + semantic inference)
    - Embeddings: OpenAI text-embedding-3-large (3072-dim, 8192 token limit)
    - Chunking: Configurable via CHUNK_SIZE env var, 15% overlap
    
    Returns:
        RAGAnything: Configured compatibility instance
    """
    global _rag_anything
    
    # Get validated settings from centralized config
    settings = get_settings()
    
    working_dir = global_args.working_dir
    
    # Government contracting entity types - SINGLE SOURCE OF TRUTH:
    # `prompts/extraction/govcon_entity_types.yaml` (loaded by EntityCatalog).
    # `VALID_ENTITY_TYPES` (re-exported from schema.py) is derived from that YAML;
    # the rendered Part D markdown is injected into the extraction prompt below
    # via `entity_types_guidance`.
    logger.info(f"📋 Loaded {len(VALID_ENTITY_TYPES)} entity types from govcon_entity_types.yaml")
    
    logger.info(f"✅ MinerU table merge: {'ENABLED' if settings.mineru_table_merge_enable else 'DISABLED (preserves per-page data)'}")
    
    # Note: All other MinerU variables (MINERU_LANG, MINERU_FORMULA_ENABLE,
    # MINERU_PDF_RENDER_TIMEOUT, CUDA_VISIBLE_DEVICES, HF_TOKEN, HF_HUB_DISABLE_SYMLINKS_WARNING, etc.)
    # are automatically inherited by MinerU subprocess from os.environ after dotenv loads .env
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # COMPATIBILITY CONTEXT-AWARE PROCESSING SETTINGS
    # ═══════════════════════════════════════════════════════════════════════════════
    # Retained for legacy content-list paths. Native LightRAG ingestion owns the
    # active parser and multimodal processing path.
    #
    # Without context: Table on p53 → "table_p53" (isolated node, no relationships)
    # With context: Table on p53 → "AL JABER AIR BASE workload table from Appendix H"
    #              → CHILD_OF relationship to APPENDIX_H_WORKLOAD_DATA
    #
    # This enables Algorithm 7 (CDRL/Section patterns) to infer parent relationships.
    #
    # IMPORTANT: Compatibility context settings are read by RAGAnythingConfig from env vars:
    #   CONTEXT_WINDOW, CONTEXT_MODE, CONTENT_FORMAT, MAX_CONTEXT_TOKENS,
    #   INCLUDE_HEADERS, INCLUDE_CAPTIONS, CONTEXT_FILTER_CONTENT_TYPES
    # ═══════════════════════════════════════════════════════════════════════════════
    
    # Create compatibility configuration - it reads context settings from env vars automatically
    # parser_output_dir: Route MinerU parsed output into a dedicated subfolder so
    # workspace state stays readable for humans: canonical LightRAG stores remain
    # at rag_storage/{workspace}/ while per-document MinerU artifacts live under
    # rag_storage/{workspace}/mineru/.
    runtime = build_raganything_runtime(
        settings,
        working_dir=working_dir,
        xai_api_key=settings.llm_binding_api_key,
        xai_base_url=settings.llm_binding_host,
        openai_api_key=settings.embedding_binding_api_key,
        config_cls=RAGAnythingConfig,
        embed_factory=openai_embed,
        embedding_func_cls=EmbeddingFunc,
        graph_storage=getattr(global_args, "graph_storage", None),
    )
    config = runtime.config
    mineru_output_dir = runtime.mineru_output_dir
    logger.info(f"📁 MinerU parser output → {mineru_output_dir}")
    
    # Log context-aware processing configuration (read from config after env var loading)
    logger.info(f"✅ Compatibility context-aware processing: {'ENABLED' if config.context_window > 0 else 'DISABLED'}")
    logger.info(f"   - context_window: {config.context_window} pages")
    logger.info(f"   - context_mode: {config.context_mode}")
    logger.info(f"   - content_format: {config.content_format}")
    logger.info(f"   - max_context_tokens: {config.max_context_tokens}")
    logger.info(f"   - include_headers: {config.include_headers}")
    logger.info(f"   - include_captions: {config.include_captions}")
    logger.info(f"   - context_filter_content_types: {getattr(config, 'context_filter_content_types', ['text'])}")
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # Prompt Configuration (govcon_prompt.py architecture)
    # ═══════════════════════════════════════════════════════════════════════════════
    # All prompts are now centralized in prompts/govcon_prompt.py:
    # - entity_extraction_json_system_prompt: GovCon extraction instructions
    # - entity_extraction_json_examples: 7 GovCon-specific examples (L⇔M, requirements, clauses, etc.)
    # - summarize_entity_descriptions: Preserve quantitative details
    # - rag_response / naive_rag_response: Shipley lifecycle support
    # - keywords_extraction: GovCon query understanding
    # 
    # Prompts are applied via PROMPTS.update(GOVCON_PROMPTS) after compatibility init
    # ═══════════════════════════════════════════════════════════════════════════════
    
    logger.info("=" * 88)
    logger.info("✅ GOVCON DOCUMENT CLASSIFIER STARTUP CHECK: CONFIGURED")
    logger.info("   chunking_func=%s", runtime.chunking_func_name)
    logger.info("   banner_template=%s", runtime.banner_template)
    logger.info("   labels=solicitation | pws | cdrl_exhibit | template | unknown")
    logger.info("   LightRAG provides the chunking_func hook; GovCon template/solicitation labeling is Theseus-owned")
    logger.info("=" * 88)

    # ═══════════════════════════════════════════════════════════════════════════════
    # Phase 1.3 (issue #124): xAI strict json_schema response_format for `extract`.
    # ═══════════════════════════════════════════════════════════════════════════════
    # Forces xAI to return EXACTLY the {name, type, description} / {source, target,
    # keywords, description} shape that LightRAG's _process_json_extraction_result
    # parser reads. Without this, json_object mode lets xAI improvise field names
    # ({entity, type} or {subject, relation, object}) — those drop on parse.
    # `type` is constrained to the 33-entity-type enum. xAI strict mode rejects
    # JSON-Schema `pattern`, so relationship keyword canonicalization remains prompt
    # + downstream normalization. Toggle via ENTITY_EXTRACTION_STRICT_SCHEMA=true.
    # ═══════════════════════════════════════════════════════════════════════════════
    lightrag_kwargs = {
        **runtime.lightrag_kwargs,
        "entity_extraction_use_json": True,
    }
    
    # LLM function for compatibility top-level + modal processors. The legacy
    # TableModalProcessor / EquationModalProcessor parse their own JSON shape
    # ({detailed_description, entity_info}); do NOT route them through the strict
    # GovCon extraction schema ({entities, relationships}) or every table falls
    # back with "Missing required fields in response".
    logger.info("✅ Compatibility modal LLM uses non-strict table/equation parser path")
    
    _rag_anything = RAGAnything(
        config=config,
        llm_model_func=runtime.modal_llm_func,
        vision_model_func=runtime.vision_model_func,
        embedding_func=runtime.embedding_func,
        lightrag_kwargs=lightrag_kwargs,
    )
    
    # CRITICAL: Ensure LightRAG is initialized before compatibility callbacks touch storage.
    result = await _rag_anything._ensure_lightrag_initialized()
    if not result.get("success", False):
        error_msg = result.get("error", "Unknown error")
        logger.error(f"Failed to initialize LightRAG: {error_msg}")
        raise RuntimeError(f"LightRAG initialization failed: {error_msg}")

    await finalize_rag_initialization(
        _rag_anything,
        settings=settings,
        working_dir=working_dir,
        modal_llm_func=runtime.modal_llm_func,
        vision_model_func=runtime.vision_model_func,
        use_strict_schema=runtime.use_strict_schema,
    )
    
    return _rag_anything


def get_rag_instance():
    """Get the global RAG-Anything instance
    
    Returns:
        RAGAnything: The initialized instance, or None if not yet initialized
    """
    return _rag_anything
