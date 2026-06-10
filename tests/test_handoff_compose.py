from src.server.handoff_compose import HandoffComposeInput, mechanical_handoff_seed


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