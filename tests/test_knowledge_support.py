from importlib import import_module

from src.ontology.govcon_kg import build_govcon_ontology_kg
from src.ontology.knowledge_support import (
    knowledge_bundle_path,
    load_knowledge_bundle,
    load_knowledge_exports,
    load_knowledge_parts,
)


KNOWLEDGE_MODULES = {
    "capture": {
        "module": "src.ontology.knowledge.capture",
        "entity_name": "Bid No-Bid Decision Framework",
    },
    "shipley": {
        "module": "src.ontology.knowledge.shipley",
        "entity_name": "Pink Team Review",
    },
    "evaluation": {
        "module": "src.ontology.knowledge.evaluation",
        "entity_name": "Adjectival Rating Scale Patterns",
    },
    "regulations": {
        "module": "src.ontology.knowledge.regulations",
        "entity_name": "DFARS Cybersecurity Requirements",
    },
    "lessons_learned": {
        "module": "src.ontology.knowledge.lessons_learned",
        "entity_name": "Explicit Benefit Linkage Rule",
    },
    "company_capabilities": {
        "module": "src.ontology.knowledge.company_capabilities",
        "entity_name": "KBR Inc",
    },
    "workload": {
        "module": "src.ontology.knowledge.workload",
        "entity_name": "Basis of Estimate Development",
    },
}


def test_all_knowledge_bundles_match_module_exports() -> None:
    for bundle_name, module_meta in KNOWLEDGE_MODULES.items():
        module = import_module(module_meta["module"])
        bundle = load_knowledge_bundle(bundle_name)

        assert knowledge_bundle_path(bundle_name).is_file()
        assert bundle["source_id"] == module.SOURCE_ID
        assert bundle["file_path"] == module.FILE_PATH
        assert bundle["entities"] == module.ENTITIES
        assert bundle["relationships"] == module.RELATIONSHIPS
        assert bundle["chunks"] == module.CHUNKS

        assert load_knowledge_exports(bundle_name) == (
            module.SOURCE_ID,
            module.FILE_PATH,
            module.ENTITIES,
            module.RELATIONSHIPS,
            module.CHUNKS,
        )

        entities, relationships, chunks = load_knowledge_parts(bundle_name)
        assert entities == module.ENTITIES
        assert relationships == module.RELATIONSHIPS
        assert chunks == module.CHUNKS


def test_build_govcon_ontology_kg_excludes_reference_only_capture_content() -> None:
    kg = build_govcon_ontology_kg()
    expected_entities = set()
    expected_relationships = 0
    expected_chunks = 0

    for bundle_name, module_meta in KNOWLEDGE_MODULES.items():
        if bundle_name == "capture":
            continue
        bundle = load_knowledge_bundle(bundle_name)
        expected_entities.add(module_meta["entity_name"])
        expected_relationships += len(bundle["relationships"])
        expected_chunks += len(bundle["chunks"])

    entity_names = {entity["entity_name"] for entity in kg["entities"]}

    assert expected_entities <= entity_names
    assert KNOWLEDGE_MODULES["capture"]["entity_name"] not in entity_names
    assert len(kg["relationships"]) == expected_relationships
    assert len(kg["chunks"]) == expected_chunks