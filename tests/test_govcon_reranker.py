from src.extraction.govcon_reranker import (
    reset_active_min_rerank_score,
    resolve_min_rerank_score,
    set_active_min_rerank_score,
)


def test_resolve_min_rerank_score_uses_active_override(monkeypatch) -> None:
    monkeypatch.setenv("MIN_RERANK_SCORE", "0.0")

    token = set_active_min_rerank_score(0.25)
    try:
        assert resolve_min_rerank_score() == 0.25
    finally:
        reset_active_min_rerank_score(token)

    assert resolve_min_rerank_score() == 0.0