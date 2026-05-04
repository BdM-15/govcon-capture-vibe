import json

from src.inference.semantic_post_process_support import (
    build_post_processing_result,
    collect_relationship_retype_updates,
    count_vdb_entries,
    heuristic_table_type_mapping,
    plan_entity_type_updates,
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


def test_collect_relationship_retype_updates_filters_and_maps() -> None:
    relationships = [
        {"source": "n1", "target": "n2", "type": "RELATED_TO"},
        {"source": "n1", "target": "n3", "type": "GOVERNED_BY"},
        {"source": "missing", "target": "n2", "type": "RELATED_TO"},
    ]
    entity_by_id = {
        "n1": {"entity_type": "requirement"},
        "n2": {"entity_type": "deliverable"},
        "n3": {"entity_type": "clause"},
    }

    assert collect_relationship_retype_updates(relationships, entity_by_id) == [
        {
            "source_id": "n1",
            "target_id": "n2",
            "old_type": "RELATED_TO",
            "new_type": "SATISFIED_BY",
        }
    ]


def test_build_post_processing_result_computes_final_counts(tmp_path) -> None:
    (tmp_path / "vdb_entities.json").write_text(json.dumps({"data": [{"id": 1}]}), encoding="utf-8")
    (tmp_path / "vdb_relationships.json").write_text(json.dumps({"data": [{"id": 1}, {"id": 2}]}), encoding="utf-8")

    result = build_post_processing_result(
        rag_storage_path=str(tmp_path),
        type_counts={"requirement": 2, "deliverable": 1},
        rel_counts={"SATISFIED_BY": 4},
        entities_corrected=3,
        relationships_inferred=5,
        relationships_synced=4,
        processing_time=12.5,
        starting_entity_count=2,
        starting_relationship_count=1,
        vdb_sync_status="success",
    )

    assert result["status"] == "success"
    assert result["final_entity_count"] == 3
    assert result["final_relationship_count"] == 4
    assert result["vdb_entity_count"] == 1
    assert result["vdb_relationship_count"] == 2


def test_plan_entity_type_updates_handles_table_hash_and_unknown() -> None:
    grouped = {
        "table": [
            {"id": "t1", "entity_name": "CDRL Matrix", "content": "deliverable table"},
        ],
        "#requirement": [
            {"id": "h1", "entity_name": "Req 1"},
        ],
        "UNKNOWN": [
            {"id": "u1", "entity_name": "Mystery"},
        ],
        "concept": [
            {"id": "c1", "entity_name": "Leave Alone"},
        ],
    }

    updates, unknown_entities, table_mapped, hash_cleaned = plan_entity_type_updates(
        grouped,
        allowed_types=["requirement", "concept"],
        table_type_mapper=heuristic_table_type_mapping,
    )

    assert updates == [
        {"id": "t1", "new_entity_type": "deliverable"},
        {"id": "h1", "new_entity_type": "requirement"},
    ]
    assert unknown_entities == [{"id": "u1", "entity_name": "Mystery"}]
    assert table_mapped == 1
    assert hash_cleaned == 1