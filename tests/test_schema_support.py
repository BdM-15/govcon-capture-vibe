from src.ontology.schema import VALID_RELATIONSHIP_TYPES
from src.ontology.schema_support import (
    INFERENCE_ONLY_RELATIONSHIP_TYPES,
    ROGUE_RELATIONSHIP_MAPPINGS,
    normalize_relationship_type,
    render_relationship_types_guidance,
)


class _Logger:
    def __init__(self):
        self.info_messages = []
        self.warning_messages = []

    def info(self, message):
        self.info_messages.append(message)

    def warning(self, message):
        self.warning_messages.append(message)


def test_render_relationship_types_guidance_contains_inference_only_block() -> None:
    guidance = render_relationship_types_guidance()

    assert "VALID RELATIONSHIP TYPES" in guidance
    assert "Inference-only types (not emitted by the LLM):" in guidance
    assert ", ".join(INFERENCE_ONLY_RELATIONSHIP_TYPES) in guidance


def test_normalize_relationship_type_maps_rogue_and_unknown_values() -> None:
    logger = _Logger()

    assert normalize_relationship_type(
        "mandates",
        valid_relationship_types=VALID_RELATIONSHIP_TYPES,
        logger=logger,
    ) == ROGUE_RELATIONSHIP_MAPPINGS["MANDATES"]
    assert logger.info_messages[-1] == "Mapped rogue relationship type 'mandates' → 'GOVERNED_BY'"

    assert normalize_relationship_type(
        "made_up_edge",
        valid_relationship_types=VALID_RELATIONSHIP_TYPES,
        fallback="RELATED_TO",
        logger=logger,
    ) == "RELATED_TO"
    assert logger.warning_messages[-1] == "⚠️ Unknown relationship type 'made_up_edge' → defaulting to 'RELATED_TO'"


def test_normalize_relationship_type_passes_through_valid_value() -> None:
    assert normalize_relationship_type(
        "evaluated by",
        valid_relationship_types=VALID_RELATIONSHIP_TYPES,
    ) == "EVALUATED_BY"