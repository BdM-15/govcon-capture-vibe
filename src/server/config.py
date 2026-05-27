"""
Server Configuration for RAG-Anything + LightRAG

Configures global_args for LightRAG server with government contracting ontology.
Uses xAI Grok for LLM and OpenAI for embeddings.

Configuration is loaded from src/core/config.py (centralized Settings class).
"""

# CRITICAL: Load .env BEFORE importing LightRAG modules
# LightRAG's chunk_token_size default: int(os.getenv("CHUNK_SIZE", 1200))
# Must set environment variables before LightRAG classes are defined
from dotenv import load_dotenv
load_dotenv(override=True)

# Now safe to import LightRAG and our config
import logging
from lightrag.api.config import global_args
from src.extraction.govcon_chunking import govcon_chunking_func

from src.core.config import get_settings
from src.ontology.schema import VALID_ENTITY_TYPES

logger = logging.getLogger(__name__)


def configure_lightrag_args():
    """
    Configure global_args for the native LightRAG server runtime.
    
    All configuration values come from the centralized Settings class.
    """
    # Get validated settings from centralized config
    settings = get_settings()
    
    # Working directory
    global_args.working_dir = settings.working_dir
    global_args.input_dir = settings.input_dir

    # Canonical LightRAG state stays on local file-backed storage for this repo.
    # Neo4j remains the graph backend, while KV/doc status/vector persistence lives
    # under rag_storage/<workspace>/ using LightRAG's default local implementations.
    global_args.kv_storage = "JsonKVStorage"
    global_args.vector_storage = "NanoVectorDBStorage"
    global_args.doc_status_storage = "JsonDocStatusStorage"
    
    # Graph Storage Configuration - Neo4j vs NetworkX
    if settings.graph_storage == "Neo4JStorage":
        from lightrag.kg.neo4j_impl import Neo4JStorage
        
        neo4j_config = {
            "uri": settings.neo4j_uri,
            "username": settings.neo4j_username,
            "password": settings.neo4j_password,
            "database": settings.neo4j_database,
        }
        
        # Create Neo4j storage instance
        global_args.graph_storage = "Neo4JStorage"  # Tell LightRAG to use Neo4j
        global_args.neo4j_config = neo4j_config     # Pass Neo4j connection details
    else:
        global_args.graph_storage = "NetworkXStorage"
    
    # Server configuration
    global_args.host = settings.host
    global_args.port = settings.port
    
    # LLM Configuration - xAI Grok (Dual-Model: Extraction uses non-reasoning, Query uses reasoning)
    global_args.llm_binding = "openai"

    # IMPORTANT: LightRAG's API server uses `llm_model` (from env `LLM_MODEL`) for /query.
    # We explicitly bind queries to the reasoning model to avoid "compliance-only" answers.
    #
    # Extraction is handled separately by RAG-Anything via src/server/initialization.py (dual-model router),
    # so setting the query model here will NOT force extraction to use reasoning.
    query_model = settings.reasoning_llm_name

    # Keep legacy fields (some older code paths may read these), but ensure the canonical fields are set.
    global_args.llm_model = query_model
    global_args.llm_model_name = query_model
    global_args.llm_binding_host = settings.llm_binding_host
    global_args.llm_binding_api_key = settings.llm_binding_api_key
    global_args.llm_api_key = settings.llm_binding_api_key
    
    # Embedding Configuration - OpenAI (MUST use OpenAI endpoint, not xAI!)
    global_args.embedding_binding = "openai"
    global_args.embedding_model_name = settings.embedding_model
    global_args.embedding_binding_host = settings.embedding_binding_host
    global_args.embedding_binding_api_key = settings.embedding_binding_api_key
    global_args.embedding_api_key = settings.embedding_binding_api_key
    global_args.embedding_dim = settings.embedding_dim
    
    # Government contracting entity types (single source of truth from YAML-derived schema)
    # LightRAG reads entity_types only from addon_params (operate.py line 2908).
    entity_types = sorted(VALID_ENTITY_TYPES)
    
    # addon_params is the sole path LightRAG uses for entity_types in extraction
    global_args.addon_params = {
        "language": "English",
        "entity_types": entity_types,
    }
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PARALLELIZATION CONFIGURATION (Semantic naming from centralized config)
    # ═══════════════════════════════════════════════════════════════════════════
    # LightRAG has three concurrency controls:
    # - max_parallel_insert: Document-level parallelism (files processed concurrently)
    # - max_async / llm_model_max_async: Chunk-level LLM concurrency within each document
    # - embedding_func_max_async: Embedding API concurrency
    #
    # Our centralized config uses semantic names for clarity:
    # - settings.max_parallel_insert → document-level (recommended: llm_max_async / 3)
    # - settings.llm_max_async → extraction LLM concurrency (higher for throughput)
    # - settings.embedding_max_async → embedding concurrency
    # - settings.post_processing_max_async → semantic inference (lower for stability)
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Document-level parallelism (how many files processed at once)
    global_args.max_parallel_insert = settings.max_parallel_insert
    
    # Chunk-level LLM concurrency (extraction throughput)
    effective_llm_async = settings.get_effective_llm_max_async()
    global_args.max_async = effective_llm_async
    
    # Embedding API concurrency
    effective_embedding_async = settings.get_effective_embedding_max_async()
    global_args.embedding_func_max_async = effective_embedding_async
    
    # Chunking configuration (optimized for focused extraction)
    # CHUNK_SIZE: Document chunking for BOTH LLM entity extraction and embeddings
    # - 8K chunks = multiple focused extraction passes = comprehensive coverage
    # - Embeddings auto-truncate to model limits via EmbeddingFunc.max_token_size
    #
    # NOTE: global_args.chunking_func is NOT consumed by lightrag.api.lightrag_server
    # — the API constructs LightRAG without forwarding this attribute. The actual
    # registration of govcon_chunking_func happens in src/server/initialization.py
    # via lightrag_kwargs={"chunking_func": govcon_chunking_func}. We set the
    # attribute here only for completeness / future LightRAG API support.
    global_args.chunking_func = govcon_chunking_func
    
    # Validate required chunking settings (centralized validation)
    settings.validate_required_settings()
    global_args.chunk_token_size = settings.chunk_size
    global_args.chunk_overlap_token_size = settings.chunk_overlap_size
    
    # Extraction input token limit (Grok supports 131K, default 100K for headroom)
    global_args.max_extract_input_tokens = settings.max_extract_input_tokens
    
    # Multimodal support
    global_args.enable_multimodal = True
    
    logger.info(f"  Parallelization: max_parallel_insert={settings.max_parallel_insert}, "
                f"llm_max_async={effective_llm_async}, embedding_max_async={effective_embedding_async}")
    logger.info(f"  Post-processing will use: max_async={settings.get_effective_post_processing_max_async()}")
    logger.info(
        "  Local state storage: kv=%s, vector=%s, doc_status=%s",
        global_args.kv_storage,
        global_args.vector_storage,
        global_args.doc_status_storage,
    )
    
    # Configuration complete - detailed startup logging happens in initialization.py


def configure_raganything_args():
    """Backward-compatible alias for older tests and migration branches."""
    configure_lightrag_args()
