from src.ontology.govcon_kg import build_govcon_ontology_kg
from src.ontology.knowledge.capture import (
    CHUNKS,
    ENTITIES,
    FILE_PATH,
    RELATIONSHIPS,
    SOURCE_ID,
)
from src.ontology.knowledge_support import (
    knowledge_bundle_path,
    load_knowledge_bundle,
    load_knowledge_parts,
)


def test_load_knowledge_bundle_matches_capture_exports() -> None:
    bundle = load_knowledge_bundle("capture")

    assert knowledge_bundle_path("capture").is_file()
    assert bundle["source_id"] == SOURCE_ID
    assert bundle["file_path"] == FILE_PATH
    assert bundle["entities"] == ENTITIES
    assert bundle["relationships"] == RELATIONSHIPS
    assert bundle["chunks"] == CHUNKS

    entities, relationships, chunks = load_knowledge_parts("capture")
    assert entities == ENTITIES
    assert relationships == RELATIONSHIPS
    assert chunks == CHUNKS


def test_build_govcon_ontology_kg_includes_file_backed_capture_content() -> None:
    kg = build_govcon_ontology_kg()

    assert any(
        entity["entity_name"] == "Bid No-Bid Decision Framework"
        for entity in kg["entities"]
    )
    assert any(
        relationship["src_id"] == "Capture Plan Development"
        for relationship in kg["relationships"]
    )
    assert any(
        "price-to-win" in chunk["content"].lower()
        for chunk in kg["chunks"]
    )