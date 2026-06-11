import asyncio
import httpx
from types import SimpleNamespace

from src.server.handoff_compose import (
    HandoffComposeInput,
    compose_insight_handoff,
    mechanical_handoff_seed,
)


def test_mechanical_handoff_seed_includes_quote_and_question() -> None:
    result = mechanical_handoff_seed(
        HandoffComposeInput(
            source_chat_title="Cash flow thread",
            message_index=2,
            quote="NET 30 terms stress receivables.",
            framing_question="Show me the evidence.",
            prior_user_question="What payment risks matter?",
        )
    )

    assert result.composed is False
    assert result.title == "NET 30 terms stress receivables."
    assert "Cash flow thread" in result.seed_prompt
    assert "> NET 30 terms stress receivables." in result.seed_prompt
    assert "Show me the evidence." in result.seed_prompt
    assert "What payment risks matter?" in result.seed_prompt


def test_compose_insight_handoff_falls_back_on_timeout(monkeypatch) -> None:
    settings = SimpleNamespace(
        ollama_model="qwen3.5:9b",
        ollama_host="http://localhost:11434",
        ollama_compose_timeout=5.0,
    )
    payload = HandoffComposeInput(
        source_chat_title="Volume thread",
        message_index=0,
        quote="Volume II is 40 pages.",
        framing_question="Expand on Volume II requirements.",
    )

    monkeypatch.setattr("src.server.handoff_compose.is_ollama_available", lambda _: True)
    monkeypatch.setattr("src.server.handoff_compose.resolve_ollama_model", lambda _: "qwen3.5:9b")

    async def slow_chat(*args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("src.server.handoff_compose.ollama_chat", slow_chat)

    result = asyncio.run(compose_insight_handoff(payload, settings=settings))

    assert result.composed is False
    assert result.fallback_reason == "timeout"
    assert "Volume II is 40 pages." in result.seed_prompt
    assert result.model == "qwen3.5:9b"