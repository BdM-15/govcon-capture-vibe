from src.inference.neo4j_write_support import (
    log_rejected_entities,
    log_rejected_relationships,
)


class _Logger:
    def __init__(self) -> None:
        self.error_messages: list[str] = []
        self.warning_messages: list[str] = []

    def error(self, message: str) -> None:
        self.error_messages.append(message)

    def warning(self, message: str) -> None:
        self.warning_messages.append(message)


def test_log_rejected_relationships_emits_loss_report() -> None:
    logger = _Logger()

    log_rejected_relationships(
        relationships=[{"source_id": "1", "target_id": "2", "relationship_type": ""}],
        rejected_relationships=[{"source_id": "1", "target_id": "2", "relationship_type": None, "reasoning": "bad type"}],
        logger=logger,
    )

    assert logger.error_messages[1] == "❌ CRITICAL: REJECTED MALFORMED RELATIONSHIPS (DATA LOSS)"
    assert "Rejected 1 of 1 relationships due to null/empty 'relationship_type'" in logger.error_messages
    assert "  [1] Source: 1" in logger.error_messages
    assert "      Target: 2" in logger.error_messages
    assert "      Type:   None" in logger.error_messages
    assert logger.error_messages[-2] == "⚠️  INVESTIGATE: Check inference algorithms for null type generation"


def test_log_rejected_entities_emits_error_and_summary_warning() -> None:
    logger = _Logger()

    log_rejected_entities(
        [{"entity_type": "requirement"}, {"entity_name": "", "entity_type": "clause"}],
        logger=logger,
    )

    assert len(logger.error_messages) == 2
    assert logger.error_messages[0].startswith("❌ Critical Error: Entity reached Neo4j without a name!")
    assert logger.warning_messages == [
        "⚠️ Skipped 2 entities with missing names in Neo4j creation"
    ]