"""
Local BGE Reranker for govcon RAG queries.

Uses BAAI/bge-reranker-v2-m3 (XLM-RoBERTa cross-encoder, 8192 ctx, ~1.2 GB VRAM @ FP16)
to re-score query-chunk pairs AFTER LightRAG's vector/entity/relation triple-merge.
Improves chunk ordering before LLM context assembly — typically 15-25% NDCG@10 lift
on dense English RAG benchmarks (NVIDIA arXiv 2409.07691).

Wired via LightRAG's `rerank_model_func` extension point. Heavy ML imports are
deferred to first call so disabled mode pays zero import cost.

Module-level singleton: model loaded once on first query, reused for server lifetime.
"""

from __future__ import annotations

import contextvars
import logging
import time
from typing import Any

from src.core.config import get_settings

logger = logging.getLogger(__name__)

# Per-query override from UI Query Tuning (set by make_ui_query_bridges).
_active_min_rerank_score: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "govcon_active_min_rerank_score",
    default=None,
)

# Singleton state — loaded lazily by _get_reranker() on first query
_reranker_instance: Any = None
_reranker_model_name: str | None = None


def set_active_min_rerank_score(score: float | None) -> contextvars.Token[float | None]:
    """Bind the workspace/UI min rerank threshold for the current query."""
    return _active_min_rerank_score.set(score)


def reset_active_min_rerank_score(token: contextvars.Token[float | None]) -> None:
    """Restore the prior min rerank threshold after a query completes."""
    _active_min_rerank_score.reset(token)


def resolve_min_rerank_score() -> float:
    """Return per-query UI override when set, else global settings default."""
    active = _active_min_rerank_score.get()
    if active is not None:
        return float(active)
    return float(get_settings().min_rerank_score)


def _get_reranker() -> Any:
    """Lazy-load the FlagReranker singleton.

    Heavy imports (FlagEmbedding, torch) happen here, not at module import.
    Reloads if the configured model name changes between server restarts.
    """
    global _reranker_instance, _reranker_model_name
    settings = get_settings()

    if _reranker_instance is None or _reranker_model_name != settings.rerank_model:
        # Defer heavy imports until first actual use
        from FlagEmbedding import FlagReranker  # type: ignore[import-not-found]

        load_start = time.perf_counter()
        _reranker_instance = FlagReranker(
            settings.rerank_model,
            use_fp16=settings.rerank_use_fp16,
            devices=[settings.rerank_device],
        )
        _reranker_model_name = settings.rerank_model
        load_ms = (time.perf_counter() - load_start) * 1000
        logger.info(
            "✅ Loaded reranker: %s on %s (FP16=%s, cold-start=%.0fms)",
            settings.rerank_model,
            settings.rerank_device,
            settings.rerank_use_fp16,
            load_ms,
        )

    return _reranker_instance


async def govcon_rerank_func(
    query: str,
    documents: list[str],
    top_n: int | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Rerank document texts by query relevance using local BGE cross-encoder.

    Signature matches LightRAG's `rerank_model_func` contract — LightRAG
    pre-extracts chunk text and passes a list of strings, expecting index-based
    results. See `lightrag/utils.py:apply_rerank_if_enabled` and reference
    implementations in `lightrag/rerank.py` (cohere_rerank, jina_rerank).

    Args:
        query: User query string.
        documents: List of chunk text strings (already extracted by LightRAG).
        top_n: If set, return only the top N highest-scoring entries.
        **kwargs: Ignored (LightRAG does not pass min_rerank_score; use set_active_min_rerank_score).

    Returns:
        List of `{"index": int, "relevance_score": float}` dicts sorted by score
        descending. `index` refers to the position in the input `documents` list.
        Entries below `min_rerank_score` are filtered out.
    """
    if not documents:
        return []

    settings = get_settings()
    reranker = _get_reranker()

    rerank_start = time.perf_counter()
    pairs = [(query, text or "") for text in documents]
    scores = reranker.compute_score(pairs, normalize=True)
    # FlagReranker returns a single float for one pair, list for many — normalize
    if isinstance(scores, float):
        scores = [scores]

    min_score = resolve_min_rerank_score()
    all_scores = [(i, float(s)) for i, s in enumerate(scores)]
    all_scores.sort(key=lambda r: r[1], reverse=True)
    pre_filter_top = all_scores[0][1] if all_scores else 0.0

    indexed_scores = [
        {"index": i, "relevance_score": s}
        for i, s in all_scores
        if s >= min_score
    ]
    n_filtered = len(documents) - len(indexed_scores)

    elapsed_ms = (time.perf_counter() - rerank_start) * 1000
    top_score = indexed_scores[0]["relevance_score"] if indexed_scores else 0.0
    logger.info(
        "🔀 Reranked %d chunks in %.0fms | pre_filter_top=%.3f | top_score=%.3f | filtered_below_%.2f=%d",
        len(documents),
        elapsed_ms,
        pre_filter_top,
        top_score,
        min_score,
        n_filtered,
    )

    return indexed_scores[:top_n] if top_n else indexed_scores


def make_govcon_rerank_func() -> Any | None:
    """Factory returning the rerank function or None if disabled.

    Called once at server startup from `src/server/initialization.py`.
    Returning None lets LightRAG skip reranking entirely (zero overhead).
    """
    settings = get_settings()
    if not settings.enable_rerank:
        logger.info("⏭️ Local reranking DISABLED (ENABLE_RERANK=false)")
        return None

    logger.info(
        "🎯 Local reranker ENABLED: %s (device=%s, fp16=%s, min_score=%.2f)",
        settings.rerank_model,
        settings.rerank_device,
        settings.rerank_use_fp16,
        settings.min_rerank_score,
    )
    return govcon_rerank_func
