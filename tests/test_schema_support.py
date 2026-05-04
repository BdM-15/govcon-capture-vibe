from src.ontology.schema import VALID_RELATIONSHIP_TYPES
from src.ontology.schema import BOECategory, VALID_ENTITY_TYPES
from src.ontology.schema_support import (
    clean_entity_name,
    INFERENCE_ONLY_RELATIONSHIP_TYPES,
    ROGUE_RELATIONSHIP_MAPPINGS,
    normalize_boe_category,
    normalize_entity_type_payload,
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


def test_normalize_boe_category_maps_known_and_fallback_values() -> None:
    logger = _Logger()

    assert normalize_boe_category(
        "security",
        boe_categories=BOECategory,
        boe_category_mapping={"security": BOECategory.COMPLIANCE},
        fallback=BOECategory.LABOR,
        logger=logger,
    ) == BOECategory.COMPLIANCE

    assert normalize_boe_category(
        "Materials",
        boe_categories=BOECategory,
        boe_category_mapping={},
        fallback=BOECategory.LABOR,
        logger=logger,
    ) == BOECategory.MATERIALS

    assert normalize_boe_category(
        "mystery",
        boe_categories=BOECategory,
        boe_category_mapping={},
        fallback=BOECategory.LABOR,
        logger=logger,
    ) == BOECategory.LABOR
    assert logger.warning_messages[-1] == "Unmapped BOE category 'mystery' -> defaulting to 'Labor'"


def test_normalize_entity_type_payload_repairs_case_and_invalid_types() -> None:
    logger = _Logger()

    values = normalize_entity_type_payload(
        {"entity_name": "Acme", "entity_type": "Organization"},
        valid_entity_types=VALID_ENTITY_TYPES,
        logger=logger,
    )
    assert values["entity_type"] == "organization"

    values = normalize_entity_type_payload(
        {"entity_name": "Acme", "entity_type": "VendorThing"},
        valid_entity_types=VALID_ENTITY_TYPES,
        logger=logger,
    )
    assert values["entity_type"] == "concept"
    assert logger.warning_messages[-1].startswith("⚠️ Invalid entity_type 'VendorThing' for 'Acme' (valid types: ")
    assert logger.warning_messages[-1].endswith("...)")


def test_clean_entity_name_strips_leading_hashes_and_whitespace() -> None:
    assert clean_entity_name("  # Section L ") == "# Section L"
    assert clean_entity_name("# Section L ") == "Section L"
    assert clean_entity_name("No Cleanup Needed") == "No Cleanup Needed"