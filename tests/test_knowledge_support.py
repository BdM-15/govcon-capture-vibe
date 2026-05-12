import src.ontology.knowledge as knowledge_pkg
from src.ontology.govcon_kg import build_govcon_ontology_kg
from src.ontology.knowledge_support import (
    knowledge_bundle_path,
    load_knowledge_bundle,
    load_knowledge_exports,
    load_knowledge_parts,
)

# Maps bundle name → (package entities attr, rels attr, chunks attr)
_BUNDLE_PKG_EXPORTS: dict[str, tuple[str, str, str]] = {
    "shipley": ("SHIPLEY_ENTITIES", "SHIPLEY_RELATIONSHIPS", "SHIPLEY_CHUNKS"),
    "regulations": ("REGULATION_ENTITIES", "REGULATION_RELATIONSHIPS", "REGULATION_CHUNKS"),
    "evaluation": ("EVALUATION_ENTITIES", "EVALUATION_RELATIONSHIPS", "EVALUATION_CHUNKS"),
    "workload": ("WORKLOAD_ENTITIES", "WORKLOAD_RELATIONSHIPS", "WORKLOAD_CHUNKS"),
    "capture": ("CAPTURE_ENTITIES", "CAPTURE_RELATIONSHIPS", "CAPTURE_CHUNKS"),
    "lessons_learned": ("LESSONS_ENTITIES", "LESSONS_RELATIONSHIPS", "LESSONS_CHUNKS"),
    "company_capabilities": ("COMPANY_ENTITIES", "COMPANY_RELATIONSHIPS", "COMPANY_CHUNKS"),
}

# Maps bundle name → a representative entity_name that must appear in its entities list
_BUNDLE_ENTITY_FIXTURES: dict[str, str] = {
    "capture": "Bid No-Bid Decision Framework",
    "shipley": "Pink Team Review",
    "evaluation": "Adjectival Rating Scale Patterns",
    "regulations": "DFARS Cybersecurity Requirements",
    "lessons_learned": "Explicit Benefit Linkage Rule",
    "company_capabilities": "KBR Inc",
    "workload": "Basis of Estimate Development",
}


def test_all_knowledge_bundles_match_package_exports() -> None:
    for bundle_name, (ent_name, rel_name, chunk_name) in _BUNDLE_PKG_EXPORTS.items():
        bundle = load_knowledge_bundle(bundle_name)

        assert knowledge_bundle_path(bundle_name).is_file()
        assert getattr(knowledge_pkg, ent_name) == bundle["entities"]
        assert getattr(knowledge_pkg, rel_name) == bundle["relationships"]
        assert getattr(knowledge_pkg, chunk_name) == bundle["chunks"]

        entities, relationships, chunks = load_knowledge_parts(bundle_name)
        assert entities == bundle["entities"]
        assert relationships == bundle["relationships"]
        assert chunks == bundle["chunks"]

        _source_id, _file_path, e, r, c = load_knowledge_exports(bundle_name)
        assert e == bundle["entities"]
        assert r == bundle["relationships"]
        assert c == bundle["chunks"]


def test_build_govcon_ontology_kg_includes_all_bundle_content() -> None:
    kg = build_govcon_ontology_kg()
    expected_entities = set()
    expected_relationships = 0
    expected_chunks = 0

    for bundle_name, entity_name in _BUNDLE_ENTITY_FIXTURES.items():
        bundle = load_knowledge_bundle(bundle_name)
        expected_entities.add(entity_name)
        expected_relationships += len(bundle["relationships"])
        expected_chunks += len(bundle["chunks"])

    entity_names = {entity["entity_name"] for entity in kg["entities"]}

    assert expected_entities <= entity_names
    assert len(kg["relationships"]) == expected_relationships
    assert len(kg["chunks"]) == expected_chunks