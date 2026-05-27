"""
Centralized Configuration for GovCon Capture Vibe
==================================================

Single source of truth for all environment variables.
Uses Pydantic Settings for validation and type safety.

Usage:
    from src.core.config import get_settings
    
    settings = get_settings()
    print(settings.llm_max_async)  # Typed, validated value

Architecture:
    - This file: Schema/structure with defaults and validation
    - .env file: Runtime values specific to your environment
    - .env.example: Template for new developers (committed to git)

CRITICAL: This module must be imported AFTER load_dotenv() in entry points.
LightRAG evaluates os.getenv() at import time for dataclass defaults.
"""

import os
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


def effective_async(max_async: int | None, specific: int) -> int:
    """Return legacy MAX_ASYNC override when present, else per-domain value."""
    return max_async if max_async is not None else specific


def missing_required_settings_errors(settings) -> list[str]:
    """Collect missing required-settings errors for startup validation."""
    errors = []

    if not settings.llm_binding_api_key:
        errors.append("LLM_BINDING_API_KEY is required")

    if not settings.embedding_binding_api_key:
        errors.append("EMBEDDING_BINDING_API_KEY is required")

    if not settings.chunk_size:
        errors.append("CHUNK_SIZE is required (no safe default exists)")

    if not settings.chunk_overlap_size:
        errors.append("CHUNK_OVERLAP_SIZE is required (no safe default exists)")

    if settings.graph_storage == "Neo4JStorage" and not settings.neo4j_password:
        errors.append("NEO4J_PASSWORD is required when using Neo4JStorage")

    return errors


def validate_required_settings(settings) -> None:
    """Raise ValueError when required settings are missing."""
    errors = missing_required_settings_errors(settings)
    if errors:
        raise ValueError(
            "Missing required configuration:\n  - "
            + "\n  - ".join(errors)
            + "\n\nPlease check your .env file."
        )


class Settings(BaseSettings):
    """
    Validated configuration for GovCon Capture Vibe.
    
    All environment variables are loaded from .env and validated at startup.
    Use get_settings() to access the cached singleton instance.
    """
    
    # ═══════════════════════════════════════════════════════════════════════════
    # LLM CONFIGURATION (xAI Grok)
    # ═══════════════════════════════════════════════════════════════════════════
    llm_binding_host: str = Field(
        default="https://api.x.ai/v1",
        description="LLM API endpoint (xAI Grok)"
    )
    llm_binding_api_key: Optional[str] = Field(
        default=None,
        description="xAI API key (required for LLM operations)"
    )
    # Per-role LLM models. Env var names match LightRAG 1.5.0's native role registry
    # (lightrag/api/config.py reads EXTRACT_LLM_MODEL / QUERY_LLM_MODEL / KEYWORD_LLM_MODEL
    # / VLM_LLM_MODEL at import time). POST_PROCESS_LLM_MODEL is our addition for the
    # src/inference/ semantic post-processor (not a LightRAG role, but kept in the same naming scheme).
    # Python attribute names retain the legacy `*_llm_name` suffix to keep call-site
    # churn minimal; only the .env variable names changed.
    extraction_llm_name: str = Field(
        default="grok-4-1-fast-non-reasoning",
        validation_alias="EXTRACT_LLM_MODEL",
        description="Non-reasoning model for entity extraction (LightRAG `extract` role)"
    )
    reasoning_llm_name: str = Field(
        default="grok-4.20-0309-reasoning",
        validation_alias="QUERY_LLM_MODEL",
        description="Reasoning model for queries (LightRAG `query` role) — grok-4.20 = lowest hallucination + strict adherence"
    )
    post_processing_llm_name: str = Field(
        default="grok-4-1-fast-reasoning",
        validation_alias="POST_PROCESS_LLM_MODEL",
        description="Fast reasoning model for src/inference/ post-processing algorithms (NOT a LightRAG role)"
    )
    keyword_llm_name: str = Field(
        default="grok-4-1-fast-non-reasoning",
        validation_alias="KEYWORD_LLM_MODEL",
        description="Non-reasoning model for query-time keyword extraction (LightRAG `keyword` role)"
    )
    vlm_llm_name: str = Field(
        default="grok-4-1-fast-non-reasoning",
        validation_alias="VLM_LLM_MODEL",
        description="Non-reasoning model for VLM table/image/equation analysis (LightRAG `vlm` role)"
    )
    llm_timeout: int = Field(
        default=600,
        description="LLM timeout in seconds (10 min for complex chunks)"
    )
    llm_max_output_tokens: int = Field(
        default=128000,
        description="Maximum output tokens for LLM responses"
    )
    llm_max_retries: int = Field(
        default=5,
        description="Maximum retries for failed LLM calls"
    )
    llm_model_temperature: float = Field(
        default=0.1,
        description="LLM temperature (low for deterministic output)"
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # EMBEDDING CONFIGURATION (OpenAI)
    # MUST use OpenAI endpoint, not xAI - xAI doesn't support embeddings
    # ═══════════════════════════════════════════════════════════════════════════
    embedding_binding_host: str = Field(
        default="https://api.openai.com/v1",
        description="Embedding API endpoint (OpenAI)"
    )
    embedding_binding_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key for embeddings (required)"
    )
    embedding_model: str = Field(
        default="text-embedding-3-large",
        description="Embedding model name"
    )
    embedding_dim: int = Field(
        default=3072,
        description="Embedding dimension (must match model)"
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PARALLELIZATION SETTINGS
    # Semantic naming for clarity on what each setting controls
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Document-level: How many documents to process concurrently
    # LightRAG recommends 2-10, typically llm_max_async / 3
    max_parallel_insert: int = Field(
        default=4,
        description="Concurrent document processing (file-level parallelism)"
    )
    
    # LLM API rate limit for extraction (higher for throughput)
    llm_max_async: int = Field(
        default=16,
        description="Concurrent LLM calls during extraction"
    )
    
    # Embedding API rate limit (usually matches LLM)
    embedding_max_async: int = Field(
        default=16,
        description="Concurrent embedding API calls"
    )
    
    # Post-processing parallelism (lower for stability with complex prompts)
    post_processing_max_async: int = Field(
        default=8,
        description="Concurrent LLM calls during semantic inference (lower for stability)"
    )
    
    # Legacy support: MAX_ASYNC overrides all async settings if explicitly set
    # This maintains backward compatibility with existing .env files
    max_async: Optional[int] = Field(
        default=None,
        description="Global override for all async settings (legacy compatibility)"
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NEO4J CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════
    graph_storage: str = Field(
        default="NetworkXStorage",
        description="Graph storage type: Neo4JStorage or NetworkXStorage"
    )
    neo4j_uri: str = Field(
        default="neo4j://localhost:7687",
        description="Neo4j connection URI"
    )
    neo4j_username: str = Field(
        default="neo4j",
        description="Neo4j username"
    )
    neo4j_password: Optional[str] = Field(
        default=None,
        description="Neo4j password"
    )
    neo4j_database: str = Field(
        default="neo4j",
        description="Neo4j database name"
    )
    # Workspace for multi-tenant isolation (used for both storage and Neo4j)
    workspace: str = Field(
        default="default",
        description="Current workspace name - used for both RAG storage and Neo4j graph isolation"
    )
    
    @property
    def neo4j_workspace(self) -> str:
        """Neo4j workspace always matches the main workspace for consistency."""
        return self.workspace
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SERVER CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════
    host: str = Field(
        default="localhost",
        description="Server host address"
    )
    port: int = Field(
        default=9621,
        description="Server port"
    )
    working_dir: str = Field(
        default="./rag_storage",
        description="RAG storage directory"
    )
    input_dir: str = Field(
        default="./inputs/uploaded",
        description="Document upload directory"
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CHUNKING CONFIGURATION
    # These have no safe defaults - must be explicitly set in .env
    # ═══════════════════════════════════════════════════════════════════════════
    chunk_size: Optional[int] = Field(
        default=None,
        description="Chunk size in tokens (required - no safe default)"
    )
    chunk_overlap_size: Optional[int] = Field(
        default=None,
        description="Chunk overlap in tokens (required - no safe default)"
    )
    max_extract_input_tokens: int = Field(
        default=100000,
        description="Max tokens per extraction LLM call (Grok supports 131K context)"
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # BATCH PROCESSING
    # ═══════════════════════════════════════════════════════════════════════════
    enable_post_processing: bool = Field(
        default=True,
        description="Enable semantic post-processing after batch completion (relationship algorithms and optional enrichment)"
    )
    batch_timeout_seconds: int = Field(
        default=30,
        description="Seconds to wait after last document before triggering semantic enhancement"
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # DOMAIN ONTOLOGY BOOTSTRAP
    # ═══════════════════════════════════════════════════════════════════════════
    auto_bootstrap_ontology: bool = Field(
        default=True,
        description="Automatically bootstrap GovCon domain ontology on workspace creation. "
                    "Set to False for testing or when manual control is needed."
    )
    ontology_bootstrap_force: bool = Field(
        default=False,
        description="Force re-bootstrap even if already done. Useful for ontology updates."
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # NATIVE LIGHTRAG PARSER ROUTING + MINERU CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════
    lightrag_parser: str = Field(
        default="pdf:mineru-ite,doc:mineru-ite,docx:native-ite,ppt*:mineru-ite,xls*:mineru-t",
        validation_alias="LIGHTRAG_PARSER",
        description="LightRAG-native parser routing rules, e.g. pdf:mineru-ite,docx:native-ite; unmatched files use legacy fallback"
    )
    mineru_api_mode: str = Field(
        default="local",
        validation_alias="MINERU_API_MODE",
        description="LightRAG MinerU API mode: local or official"
    )
    mineru_local_endpoint: str = Field(
        default="http://localhost:8888",
        validation_alias="MINERU_LOCAL_ENDPOINT",
        description="Base URL for a self-hosted MinerU API when MINERU_API_MODE=local"
    )
    mineru_official_endpoint: str = Field(
        default="https://mineru.net",
        validation_alias="MINERU_OFFICIAL_ENDPOINT",
        description="Base URL for MinerU official API when MINERU_API_MODE=official"
    )
    mineru_api_token: Optional[str] = Field(
        default=None,
        validation_alias="MINERU_API_TOKEN",
        description="MinerU official API token; required only when MINERU_API_MODE=official"
    )
    mineru_local_backend: str = Field(
        default="pipeline",
        validation_alias=AliasChoices("MINERU_LOCAL_BACKEND", "MINERU_BACKEND"),
        description="MinerU local backend passed to LightRAG's native MinerU client"
    )
    mineru_local_parse_method: str = Field(
        default="auto",
        validation_alias=AliasChoices("MINERU_LOCAL_PARSE_METHOD", "PARSE_METHOD"),
        description="MinerU local parse method passed to LightRAG's native MinerU client"
    )
    mineru_language: str = Field(
        default="en",
        validation_alias=AliasChoices("MINERU_LANGUAGE", "MINERU_LANG"),
        description="MinerU language hint passed to LightRAG's native MinerU client"
    )
    max_parallel_parse_native: int = Field(
        default=5,
        validation_alias="MAX_PARALLEL_PARSE_NATIVE",
        description="LightRAG native parser worker concurrency"
    )
    max_parallel_parse_mineru: int = Field(
        default=1,
        validation_alias="MAX_PARALLEL_PARSE_MINERU",
        description="LightRAG MinerU parser worker concurrency"
    )
    max_parallel_parse_docling: int = Field(
        default=1,
        validation_alias="MAX_PARALLEL_PARSE_DOCLING",
        description="LightRAG Docling parser worker concurrency"
    )
    max_parallel_analyze: int = Field(
        default=5,
        validation_alias="MAX_PARALLEL_ANALYZE",
        description="LightRAG multimodal analysis worker concurrency"
    )
    vlm_process_enable: bool = Field(
        default=True,
        validation_alias="VLM_PROCESS_ENABLE",
        description="Enable LightRAG native VLM multimodal analysis for routed i/t/e content"
    )

    # Legacy RAG-Anything / MinerU names retained while the migration finishes.
    parser: str = Field(
        default="mineru",
        description="Document parser: mineru or docling"
    )
    parse_method: str = Field(
        default="auto",
        description="Parse method: auto, ocr, or txt"
    )
    mineru_device_mode: str = Field(
        default="auto",
        description="MinerU device: cuda, cpu, or auto"
    )
    mineru_backend: str = Field(
        default="pipeline",
        description="MinerU 3.0 backend: pipeline | hybrid-auto-engine | vlm-auto-engine | hybrid-http-client | vlm-http-client. "
                    "MUST be explicit — 3.0 default changed from pipeline to hybrid-auto-engine."
    )
    enable_image_processing: bool = Field(
        default=True,
        description="Enable image extraction from documents"
    )
    enable_table_processing: bool = Field(
        default=True,
        description="Enable table extraction from documents"
    )
    enable_equation_processing: bool = Field(
        default=True,
        description="Enable equation extraction from documents"
    )
    mineru_table_merge_enable: bool = Field(
        default=False,
        description="Enable MinerU cross-page table merging. DISABLED by default to preserve "
                    "per-page table images and data (prevents data loss on continuation pages). "
                    "Context-aware processing connects related tables via semantic inference."
    )
    

    
    # ═══════════════════════════════════════════════════════════════════════════
    # CONTEXT-AWARE PROCESSING (RAG-Anything)
    # ═══════════════════════════════════════════════════════════════════════════
    context_window: int = Field(
        default=2,
        description="Pages of surrounding context for tables/images"
    )
    context_mode: str = Field(
        default="page",
        description="Context extraction mode: page or chunk"
    )
    max_context_tokens: int = Field(
        default=3000,
        description="Maximum tokens for context extraction"
    )
    include_headers: bool = Field(
        default=True,
        description="Include section headers in context"
    )
    include_captions: bool = Field(
        default=True,
        description="Include table/figure captions in context"
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # LOCAL RERANKER (Phase 1: BAAI/bge-reranker-v2-m3)
    # Re-scores chunks after LightRAG's vector/entity/relation triple-merge.
    # Loaded once at first query (~5s cold start, ~1.2GB VRAM @ FP16).
    # Disabled by default — flip ENABLE_RERANK=true to activate.
    # ═══════════════════════════════════════════════════════════════════════════
    enable_rerank: bool = Field(
        default=False,
        description="Enable local cross-encoder reranking of retrieved chunks"
    )
    rerank_model: str = Field(
        default="BAAI/bge-reranker-v2-m3",
        description="HuggingFace model id for the local reranker (8192 ctx, multilingual)"
    )
    rerank_device: str = Field(
        default="cuda",
        description="Reranker device: 'cuda' (RTX 4060) or 'cpu' fallback"
    )
    rerank_use_fp16: bool = Field(
        default=True,
        description="Use FP16 inference (halves VRAM, ~2x speedup on Ada-gen GPUs)"
    )
    min_rerank_score: float = Field(
        default=0.0,
        description="Filter chunks with rerank score below this threshold (0.0 = no filter)"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra env vars not in model
        # Map environment variable names to field names (for non-matching names)
        # Pydantic automatically maps UPPER_CASE env vars to lower_case fields

    # ═══════════════════════════════════════════════════════════════════════════
    # PROPERTY ALIASES for cleaner code access
    # ═══════════════════════════════════════════════════════════════════════════
    
    @property
    def llm_host(self) -> str:
        """Alias for llm_binding_host."""
        return self.llm_binding_host
    
    @property
    def llm_api_key(self) -> Optional[str]:
        """Alias for llm_binding_api_key."""
        return self.llm_binding_api_key

    # ═══════════════════════════════════════════════════════════════════════════
    # HELPER METHODS for backward compatibility with MAX_ASYNC
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_effective_llm_max_async(self) -> int:
        """Get effective LLM max async (legacy MAX_ASYNC override if set)."""
        return effective_async(self.max_async, self.llm_max_async)
    
    def get_effective_embedding_max_async(self) -> int:
        """Get effective embedding max async (legacy MAX_ASYNC override if set)."""
        return effective_async(self.max_async, self.embedding_max_async)
    
    def get_effective_post_processing_max_async(self) -> int:
        """Get effective post-processing max async (legacy MAX_ASYNC override if set)."""
        return effective_async(self.max_async, self.post_processing_max_async)
    
    def validate_required_settings(self) -> None:
        """
        Validate that required settings are present.
        Call this at startup to fail fast with clear error messages.
        """
        validate_required_settings(self)


# Module-level cache for settings singleton
_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get the cached Settings singleton.
    
    The settings are loaded once from .env and cached for the lifetime of the process.
    This ensures consistent configuration across all modules.
    
    Returns:
        Settings: Validated configuration object
    
    Example:
        from src.core.config import get_settings
        
        settings = get_settings()
        print(settings.llm_max_async)  # → 16
    """
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


def reset_settings() -> None:
    """
    Reset the settings cache (useful for testing).
    
    After calling this, the next get_settings() call will reload from .env.
    """
    global _settings_instance
    _settings_instance = None
