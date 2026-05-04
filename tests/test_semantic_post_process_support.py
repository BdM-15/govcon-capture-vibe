import json

from src.inference.semantic_post_process_support import (
    count_vdb_entries,
    heuristic_table_type_mapping,
    resolve_generic_relationship,
)


def test_count_vdb_entries_handles_list_and_missing_paths(tmp_path) -> None:
    assert count_vdb_entries("", "vdb_entities.json") is None
    assert count_vdb_entries(str(tmp_path), "missing.json") is None

    path = tmp_path / "vdb_entities.json"
    path.write_text(json.dumps({"data": [{"id": 1}, {"id": 2}]}), encoding="utf-8")
    assert count_vdb_entries(str(tmp_path), "vdb_entities.json") == 2


def test_resolve_generic_relationship_maps_known_pairs_only() -> None:
    assert resolve_generic_relationship("RELATED_TO", "requirement", "deliverable") == "SATISFIED_BY"
    assert resolve_generic_relationship("RELATED_TO", "foo", "bar") == "RELATED_TO"
    assert resolve_generic_relationship("GOVERNED_BY", "requirement", "clause") == "GOVERNED_BY"


def test_heuristic_table_type_mapping_uses_content_fallback() -> None:
    assert heuristic_table_type_mapping(
        {"entity_name": "Table 1", "content": "CDRL deliverable matrix dd form 1423"}
    ) == "deliverable"
    assert heuristic_table_type_mapping(
        {"entity_name": "Monthly workload", "content": "estimated monthly aircraft visit data"}
    ) == "requirement"
    assert heuristic_table_type_mapping(
        {"entity_name": "Unknown", "content": "plain text with no signal"}
    ) == "concept"