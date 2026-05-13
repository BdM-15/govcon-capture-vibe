from src.inference.entity_operations import (
    count_types,
    create_retyping_prompt,
    identify_forbidden_entities,
    validate_no_forbidden_types,
)


class _Logger:
    def __init__(self):
        self.info_msgs = []
        self.debug_msgs = []

    def info(self, message):
        self.info_msgs.append(message)

    def debug(self, message):
        self.debug_msgs.append(message)


def test_identify_forbidden_entities_fixes_hash_corruption_and_blanks() -> None:
    entities = [
        {"entity_name": "A", "entity_type": "#concept"},
        {"entity_name": "B", "entity_type": "table"},
        {"entity_name": "C", "entity_type": ""},
        {"entity_name": "D", "entity_type": "organization"},
    ]
    logger = _Logger()

    forbidden = identify_forbidden_entities(entities, logger=logger)

    assert [entity["entity_name"] for entity in forbidden] == ["B", "C"]
    assert entities[0]["entity_type"] == "concept"
    assert entities[2]["entity_type"] == "UNKNOWN"
    assert any("Fixed corruption" in msg for msg in logger.debug_msgs)
    assert any("Found 2 entities" in msg for msg in logger.info_msgs)


def test_create_retyping_prompt_and_validation_helpers() -> None:
    prompt = create_retyping_prompt(
        [
            {
                "entity_name": "MCPP II",
                "description": "Government program for modernization.",
                "entity_type": "UNKNOWN",
            }
        ]
    )

    assert "ALLOWED ENTITY TYPES" in prompt
    assert "MCPP II" in prompt
    assert "Current type: UNKNOWN" in prompt

    assert count_types({"a": "concept", "b": "organization", "c": "concept"}) == {
        "concept": 2,
        "organization": 1,
    }

    ok, violations = validate_no_forbidden_types(
        [
            {"entity_name": "Good", "entity_type": "organization"},
            {"entity_name": "Bad", "entity_type": "UNKNOWN"},
        ]
    )
    assert ok is False
    assert violations == ["Bad (UNKNOWN)"]