"""
RAG-Anything Initialization Module

This module handles the initialization of the RAG-Anything instance with:
- Custom entity extraction prompts (govcon_lightrag_json.txt, Parts A-L)
- Government contracting ontology (catalog-driven entity types, canonical relationship set)
- Multimodal document processing (MinerU parser)
- Cloud LLM integration (xAI Grok extraction + fast-reasoning post-processing + grok-4.20 queries + OpenAI embeddings)
"""

# CRITICAL: Ensure .env is loaded before LightRAG imports
# This file is imported by raganything_server.py which loads .env first
# But we import it here too for safety if this module is used standalone
import os
from dotenv import load_dotenv
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
from src.server.initialization_support import (
    build_raganything_runtime,
    configure_mineru_environment,
)
from src.server.rag_post_init import finalize_rag_initialization
from src.utils.time_utils import to_local_iso

logger = logging.getLogger(__name__)

# Global RAG-Anything instance
_rag_anything = None


async def initialize_raganything():
    """Initialize RAG-Anything instance for multimodal document processing
    
    Configuration:
    - Parser: MinerU (multimodal - images, tables, equations)
    - Entity Types: ontology-driven government contracting types
    - Extraction LLM: xAI Grok-4-fast-non-reasoning (literal format compliance)
    - Reasoning LLM: xAI grok-4.20-0309-reasoning (queries + semantic inference)
    - Embeddings: OpenAI text-embedding-3-large (3072-dim, 8192 token limit)
    - Chunking: Configurable via CHUNK_SIZE env var, 15% overlap
    
    Returns:
        RAGAnything: Configured instance ready for document ingestion
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
    # RAG-ANYTHING CONTEXT-AWARE PROCESSING (Issue #62)
    # ═══════════════════════════════════════════════════════════════════════════════
    # When processing multimodal content (tables, images, equations), RAG-Anything
    # can extract surrounding page context to provide section awareness.
    #
    # Without context: Table on p53 → "table_p53" (isolated node, no relationships)
    # With context: Table on p53 → "AL JABER AIR BASE workload table from Appendix H"
    #              → CHILD_OF relationship to APPENDIX_H_WORKLOAD_DATA
    #
    # This enables Algorithm 7 (CDRL/Section patterns) to infer parent relationships.
    #
    # IMPORTANT: Context settings are read by RAGAnythingConfig from env vars:
    #   CONTEXT_WINDOW, CONTEXT_MODE, CONTENT_FORMAT, MAX_CONTEXT_TOKENS,
    #   INCLUDE_HEADERS, INCLUDE_CAPTIONS, CONTEXT_FILTER_CONTENT_TYPES
    # ═══════════════════════════════════════════════════════════════════════════════
    
    # Create RAG-Anything configuration - it reads context settings from env vars automatically
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
    logger.info(f"✅ RAG-Anything context-aware processing: {'ENABLED' if config.context_window > 0 else 'DISABLED'}")
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
    # Prompts are applied via PROMPTS.update(GOVCON_PROMPTS) after RAG-Anything init
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
    
    # LLM function for RAGAnything top-level + modal processors. RAGAnything's
    # TableModalProcessor / EquationModalProcessor parse their own JSON shape
    # ({detailed_description, entity_info}); do NOT route them through the strict
    # GovCon extraction schema ({entities, relationships}) or every table falls
    # back with "Missing required fields in response".
    logger.info("✅ RAG-Anything modal LLM uses non-strict table/equation parser path")
    
    _rag_anything = RAGAnything(
        config=config,
        llm_model_func=runtime.modal_llm_func,
        vision_model_func=runtime.vision_model_func,
        embedding_func=runtime.embedding_func,
        lightrag_kwargs=lightrag_kwargs,
    )
    
    # CRITICAL: Ensure LightRAG is initialized BEFORE any document processing
    # This is required because process_document_complete_lightrag_api() accesses
    # self.lightrag.doc_status BEFORE calling _ensure_lightrag_initialized()
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
