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
from src.server.doc_status_compat import apply_doc_status_compatibility_shim
from src.server.llm_routing import build_role_llm_routing
from src.server.multimodal_setup import configure_multimodal_stack
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
    
    # API credentials from centralized config
    xai_api_key = settings.llm_binding_api_key
    xai_base_url = settings.llm_binding_host
    openai_api_key = settings.embedding_binding_api_key
    working_dir = global_args.working_dir
    
    # Government contracting entity types - SINGLE SOURCE OF TRUTH:
    # `prompts/extraction/govcon_entity_types.yaml` (loaded by EntityCatalog).
    # `VALID_ENTITY_TYPES` (re-exported from schema.py) is derived from that YAML;
    # the rendered Part D markdown is injected into the extraction prompt below
    # via `entity_types_guidance`.
    logger.info(f"📋 Loaded {len(VALID_ENTITY_TYPES)} entity types from govcon_entity_types.yaml")
    
    # MinerU configuration from centralized settings
    parser = settings.parser
    parse_method = settings.parse_method
    enable_image = settings.enable_image_processing
    enable_table = settings.enable_table_processing
    enable_equation = settings.enable_equation_processing
    device = settings.mineru_device_mode
    
    # CRITICAL: MinerU reads MINERU_DEVICE_MODE from environment, NOT from RAGAnythingConfig
    # Ensure it's set in the current process environment so MinerU subprocess inherits it
    # NOTE: MinerU 3.0 removed the -d CLI flag; device is managed internally by the API service.
    # The environment variable is still read by MinerU's internal configuration.
    os.environ["MINERU_DEVICE_MODE"] = device
    
    # CRITICAL: Disable MinerU cross-page table merging (Issue #65, MinerU #4311)
    # When tables span multiple pages, MinerU's merge logic keeps only the first page's
    # img_path and table_body, resulting in EMPTY data for continuation pages.
    # Per MinerU maintainer @myhloli: Set MINERU_TABLE_MERGE_ENABLE=0 to preserve per-page data.
    # Our context-aware processing + semantic inference will connect related tables via CHILD_OF.
    table_merge_value = "1" if settings.mineru_table_merge_enable else "0"
    os.environ["MINERU_TABLE_MERGE_ENABLE"] = table_merge_value
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
    workspace_dir = os.path.join(working_dir, settings.workspace)
    mineru_output_dir = os.path.join(workspace_dir, "mineru")
    os.makedirs(mineru_output_dir, exist_ok=True)
    config = RAGAnythingConfig(
        working_dir=working_dir,
        parser_output_dir=mineru_output_dir,
        parser=parser,
        parse_method=parse_method,
        enable_image_processing=enable_image,
        enable_table_processing=enable_table,
        enable_equation_processing=enable_equation,
        # Context settings are automatically loaded from env vars by RAGAnythingConfig
    )
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
    
    role_routing = build_role_llm_routing(
        settings,
        xai_api_key=xai_api_key,
        xai_base_url=xai_base_url,
    )
    llm_model_func = role_routing.llm_model_func
    vision_model_func = role_routing.vision_model_func
    llm_model_func_wrapped = role_routing.modal_llm_func
    use_strict_schema = role_routing.use_strict_schema
    
    # Embedding function: use LightRAG's native openai_embed with built-in truncation
    # LightRAG 1.4.13 openai_embed.func accepts max_token_size for auto-truncation.
    # Use .func (unwrapped) to avoid @wrap_embedding_func_with_attrs dimension mismatch
    # when using text-embedding-3-large (3072 dims) vs default text-embedding-3-small (1536).
    from functools import partial
    embed_impl = getattr(openai_embed, "func", openai_embed)
    embed_fn = partial(
        embed_impl,
        model=settings.embedding_model,
        api_key=openai_api_key,
        max_token_size=8192,
    )

    embedding_dim = settings.embedding_dim

    embedding_func = EmbeddingFunc(
        embedding_dim=embedding_dim,
        max_token_size=8192,
        func=embed_fn,
    )
    
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
    
    # Build lightrag_kwargs with configuration
    # LLM timeout configuration for complex chunks (360s default was insufficient for chunk 8)
    llm_timeout = settings.llm_timeout

    # Import the GovCon chunking function (non-invasive doc-type classifier + banner
    # injection). LightRAG's API server constructs LightRAG without passing
    # chunking_func, so setting global_args.chunking_func has no effect — we must
    # inject it via lightrag_kwargs. See src/extraction/govcon_chunking.py.
    from src.extraction.govcon_chunking import BANNER_TEMPLATE, govcon_chunking_func
    logger.info("=" * 88)
    logger.info("✅ GOVCON DOCUMENT CLASSIFIER STARTUP CHECK: CONFIGURED")
    logger.info("   chunking_func=src.extraction.govcon_chunking.govcon_chunking_func")
    logger.info("   banner_template=%s", BANNER_TEMPLATE)
    logger.info("   labels=solicitation | pws | cdrl_exhibit | template | unknown")
    logger.info("   LightRAG provides the chunking_func hook; GovCon template/solicitation labeling is Theseus-owned")
    logger.info("=" * 88)

    # Local BGE reranker (optional — gated by ENABLE_RERANK env var).
    # Returns None when disabled, in which case LightRAG skips reranking entirely.
    from src.extraction.govcon_reranker import make_govcon_rerank_func
    rerank_func = make_govcon_rerank_func()

    # ═══════════════════════════════════════════════════════════════════════════════
    # entity_types_guidance — rendered from prompts/extraction/govcon_entity_types.yaml
    # ═══════════════════════════════════════════════════════════════════════════════
    # LightRAG 1.5.0 dropped the `entity_types: list` shape (and hard-fails the
    # ENTITY_TYPES env var). The substitution token is `{entity_types_guidance}`,
    # a single string injected into the extraction prompt at the PART D anchor.
    #
    # Phase 1.1c (#126) of epic #124: the full Part D markdown is generated from
    # the canonical YAML catalog (single source of truth shared with schema.py's
    # `VALID_ENTITY_TYPES`). The inline Part D copy was deleted from
    # `prompts/extraction/govcon_lightrag_json.txt` to eliminate drift risk.
    # ═══════════════════════════════════════════════════════════════════════════════
    from src.ontology.entity_catalog import get_default_catalog
    entity_types_guidance = get_default_catalog().render_part_d()

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
    role_llm_configs = role_routing.role_llm_configs

    lightrag_kwargs = {
        "addon_params": {
            "entity_types_guidance": entity_types_guidance,
            # Prompt text still comes from GOVCON_PROMPTS; JSON examples are loaded
            # from prompts/entity_type/govcon.yaml via LightRAG's prompt profile.
            "entity_type_prompt_file": "govcon.yaml",
            "language": "English",
        },
        # Phase 1.2 (issue #124): native JSON structured-output extraction.
        # LightRAG uses entity_extraction_json_* prompt keys and
        # _process_json_extraction_result (json_repair-based parser).
        "entity_extraction_use_json": True,
        # Chunking configuration comes from environment variables:
        # - CHUNK_SIZE controls chunk_token_size (default: 4096)
        # - CHUNK_OVERLAP_SIZE controls chunk_overlap_token_size (default: 600)
        # LightRAG reads these at dataclass field initialization time
        "chunking_func": govcon_chunking_func,
        
        # LLM timeout: default 180s causes Worker timeout (2×=360s) failures on complex chunks
        # Increased to 600s (10 min) to handle extraction from dense requirement tables
        "default_llm_timeout": llm_timeout,

        # Phase 1.0 — native per-role LLM routing (LightRAG 1.5.0)
        "role_llm_configs": role_llm_configs,
    }

    # Wire reranker only if enabled (avoid passing None which LightRAG also accepts,
    # but keeping kwargs minimal makes intent explicit in logs).
    if rerank_func is not None:
        lightrag_kwargs["rerank_model_func"] = rerank_func
        lightrag_kwargs["min_rerank_score"] = settings.min_rerank_score
    
    # Add Neo4j configuration if enabled (from config.py global_args setup)
    # Note: Neo4j connection details come from environment variables (NEO4J_URI, etc.)
    # LightRAG reads these automatically - we only need to specify graph_storage type
    if hasattr(global_args, 'graph_storage') and global_args.graph_storage == "Neo4JStorage":
        lightrag_kwargs["graph_storage"] = global_args.graph_storage
    
    # LLM function for RAGAnything top-level + modal processors. RAGAnything's
    # TableModalProcessor / EquationModalProcessor parse their own JSON shape
    # ({detailed_description, entity_info}); do NOT route them through the strict
    # GovCon extraction schema ({entities, relationships}) or every table falls
    # back with "Missing required fields in response".
    logger.info("✅ RAG-Anything modal LLM uses non-strict table/equation parser path")
    
    _rag_anything = RAGAnything(
        config=config,
        llm_model_func=llm_model_func_wrapped,
        vision_model_func=vision_model_func,
        embedding_func=embedding_func,
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

    effective_extract_kwargs = dict(getattr(_rag_anything.lightrag, "role_llm_kwargs", {}).get("extract") or {})
    effective_response_format = effective_extract_kwargs.get("response_format") or {}
    effective_schema = effective_response_format.get("json_schema") or {}
    extract_role_state = getattr(_rag_anything.lightrag, "_role_llm_states", {}).get("extract")
    extract_metadata = getattr(extract_role_state, "metadata", {}) if extract_role_state else {}
    logger.info("=" * 88)
    logger.info("🔎 EFFECTIVE EXTRACT ROLE AFTER LightRAG INIT")
    logger.info("   response_format.type=%s", effective_response_format.get("type", "<none>"))
    logger.info("   json_schema.name=%s", effective_schema.get("name", "<none>"))
    logger.info("   strict=%s", effective_schema.get("strict", "<none>"))
    logger.info("   extract_cache_identity_host=%s", extract_metadata.get("host", "<unknown>"))
    if use_strict_schema and effective_response_format.get("type") != "json_schema":
        logger.error("❌ STRICT SCHEMA EXPECTED BUT NOT EFFECTIVE — do not process documents until fixed")
    logger.info("=" * 88)

    # Verify the GovCon chunking_func actually landed on the LightRAG instance
    active_chunker = getattr(_rag_anything.lightrag, "chunking_func", None)
    chunker_name = getattr(active_chunker, "__name__", repr(active_chunker))
    if chunker_name == "govcon_chunking_func":
        logger.info("✅ GovCon chunking_func registered on LightRAG instance (banner injection active)")
        logger.info("   Every classified document chunk will start with [GOVCON_DOC: type=...; note=...]")
        logger.info("   Persisted chunks also carry govcon_doc_type metadata when classified")
    else:
        logger.warning(
            "⚠️  Active chunking_func is '%s' (expected 'govcon_chunking_func'). "
            "Doc-type banners will NOT be injected.",
            chunker_name,
        )
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # Register GovConProcessingCallback with RAG-Anything's callback system
    # ═══════════════════════════════════════════════════════════════════════════════
    from src.server.routes import get_processing_callback
    
    processing_callback = get_processing_callback()
    processing_callback.set_llm_func(llm_model_func_wrapped)
    _rag_anything.callback_manager.register(processing_callback)
    logger.info("✅ GovConProcessingCallback registered with RAG-Anything callback_manager")
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # CRITICAL FIX: Extend VDB meta_fields to preserve entity_type and description
    # ═══════════════════════════════════════════════════════════════════════════════
    # LightRAG 1.4.13 stores entity_type/description in VDB data (operate.py line 1153)
    # but lightrag.py line 720 meta_fields = {entity_name, source_id, content, file_path}
    # doesn't include them. nano_vector_db filters on meta_fields during upsert (line 112),
    # so entity_type/description get stripped without this extension.
    # TODO: Submit PR upstream to add entity_type/description to default meta_fields.
    # ═══════════════════════════════════════════════════════════════════════════════
    lightrag_instance = _rag_anything.lightrag
    
    # Extend entities VDB meta_fields
    original_entity_meta = lightrag_instance.entities_vdb.meta_fields
    extended_entity_meta = original_entity_meta | {"entity_type", "description"}
    lightrag_instance.entities_vdb.meta_fields = extended_entity_meta
    logger.info(f"✅ Extended entities_vdb.meta_fields: {extended_entity_meta}")
    
    # Extend relationships VDB meta_fields (for keywords and description)
    original_rel_meta = lightrag_instance.relationships_vdb.meta_fields
    extended_rel_meta = original_rel_meta | {"keywords", "description"}
    lightrag_instance.relationships_vdb.meta_fields = extended_rel_meta
    logger.info(f"✅ Extended relationships_vdb.meta_fields: {extended_rel_meta}")
    
    configure_multimodal_stack(
        _rag_anything,
        llm_model_func=llm_model_func_wrapped,
        vision_model_func=vision_model_func,
    )

    # ═══════════════════════════════════════════════════════════════════════════════
    # CRITICAL: REPLACE LightRAG's ENTIRE prompt system with GovCon versions
    # ═══════════════════════════════════════════════════════════════════════════════
    # LightRAG uses multiple prompts that work together:
    # - entity_extraction_json_system_prompt: Extract entities/relationships
    # - entity_extraction_json_examples: GovCon-specific extraction examples
    # - summarize_entity_descriptions: Merge duplicate entities
    # - rag_response: Answer queries using KG + documents
    # - naive_rag_response: Answer queries using documents only
    # - keywords_extraction: Parse user queries for retrieval
    # - fail_response: When no context found
    # 
    # ALL prompts are customized for government contracting / Shipley methodology
    # ═══════════════════════════════════════════════════════════════════════════════
    from lightrag.prompt import PROMPTS
    
    # Import comprehensive GovCon prompts (govcon_prompt.py - Issue #54 architecture)
    # This module contains all LightRAG-compatible prompts with GovCon domain intelligence
    from prompts.govcon_prompt import GOVCON_PROMPTS
    
    # FULL REPLACEMENT: Apply ALL GovCon prompt overrides
    # This replaces: extraction prompts, examples, summarization, RAG responses, keywords, fail_response
    PROMPTS.update(GOVCON_PROMPTS)
    
    # Log full domain intelligence stats
    extraction_prompt = GOVCON_PROMPTS.get('entity_extraction_json_system_prompt', '')
    extraction_chars = len(extraction_prompt)
    extraction_lines = extraction_prompt.count('\n')

    logger.info("✅ REPLACED LightRAG prompt system with GovCon prompt overrides")
    logger.info(f"   Extraction prompt: {extraction_chars:,} chars (~{extraction_chars//4:,} tokens), {extraction_lines:,} lines")
    logger.info(f"   Source: V8 compact frame (govcon_prompt.py builder)")
    logger.info(f"   Domain Intelligence:")
    logger.info("     • Entity catalog rendered dynamically from govcon_entity_types.yaml")
    logger.info("     • Relationship guidance rendered from schema.py 26-type canonical set")
    logger.info("     • 7 annotated RFP examples injected from prompts/entity_type/govcon.yaml")
    logger.info(f"     • Quantitative preservation rules for BOE development")
    logger.info(f"     • Compact frame + quality checks (Parts A-H)")
    logger.info(f"   Keywords examples: {len(GOVCON_PROMPTS.get('keywords_extraction_examples', []))} GovCon-specific")
    
    # Compat fix stays isolated in src/server/doc_status_compat.py.
    apply_doc_status_compatibility_shim(_rag_anything.lightrag)
    # ═════════════════════════════════════════════════════════════════════════════
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # DOMAIN ONTOLOGY BOOTSTRAP (Issue #68)
    # ═══════════════════════════════════════════════════════════════════════════════
    # Pre-load curated GovCon domain knowledge into the workspace. This provides:
    # - Zero-document queries: "What is a Color Team review?" works immediately
    # - Enhanced retrieval: Domain concepts (Shipley, FAR, BOE) connect to extracted entities
    # - Evaluation grounding: Rating scales, compliance patterns available for analysis
    #
    # Bootstrap happens ONCE per workspace (marker file prevents re-run).
    # Set AUTO_BOOTSTRAP_ONTOLOGY=False in .env to disable for testing.
    # ═══════════════════════════════════════════════════════════════════════════════
    if settings.auto_bootstrap_ontology:
        try:
            from src.ontology.bootstrap import bootstrap_govcon_ontology
            
            # CRITICAL: Use workspace-specific path, not base working_dir
            # working_dir is ./rag_storage, but workspace data is in ./rag_storage/{workspace}
            workspace_path = os.path.join(working_dir, settings.workspace)
            
            bootstrap_result = await bootstrap_govcon_ontology(
                lightrag=_rag_anything.lightrag,
                working_dir=workspace_path,
                force=settings.ontology_bootstrap_force,
            )
            
            if bootstrap_result["status"] == "success":
                logger.info(f"✅ GovCon ontology bootstrapped into workspace '{settings.workspace}': "
                          f"{bootstrap_result['entities_added']} entities, "
                          f"{bootstrap_result['relationships_added']} relationships")
            elif bootstrap_result["status"] == "already_bootstrapped":
                logger.info(f"📚 GovCon ontology already bootstrapped into workspace "
                          f"'{settings.workspace}' ({bootstrap_result['bootstrapped_at']})")
            else:
                logger.warning(f"⚠️ Ontology bootstrap: {bootstrap_result.get('error', 'unknown issue')}")
                
        except Exception as e:
            # Non-fatal - ontology is enhancement, not required for core functionality
            logger.warning(f"⚠️ Ontology bootstrap failed: {e} - continuing without domain knowledge")
    else:
        logger.info("📚 Ontology auto-bootstrap DISABLED (AUTO_BOOTSTRAP_ONTOLOGY=False)")
    
    return _rag_anything


def get_rag_instance():
    """Get the global RAG-Anything instance
    
    Returns:
        RAGAnything: The initialized instance, or None if not yet initialized
    """
    return _rag_anything
