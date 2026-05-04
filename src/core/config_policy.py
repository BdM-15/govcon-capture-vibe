"""Pure policy helpers for Settings."""

from __future__ import annotations


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