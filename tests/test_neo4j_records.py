from src.inference.neo4j_graph_io import (
    count_from_record,
    entity_names_from_records,
    entity_record_to_dict,
    group_entities_by_type,
    partition_entities_by_name,
    relationship_record_to_dict,
    type_counts_from_records,
)


def test_entity_record_to_dict_preserves_post_processing_contract() -> None:
    record = {
        "id": "node-1",
        "entity_name": "REQ-1",
        "entity_type": "requirement",
        "description": "A requirement",
        "source_id": "chunk-1",
    }

    assert entity_record_to_dict(record) == {
        "id": "node-1",
        "entity_name": "REQ-1",
        "entity_type": "requirement",
        "description": "A requirement",
        "source_id": "chunk-1",
    }


def test_relationship_record_to_dict_preserves_edge_contract() -> None:
    record = {
        "source": "node-1",
        "target": "node-2",
        "rel_type": "SATISFIED_BY",
        "weight": 0.9,
        "description": "links requirement to deliverable",
        "keywords": "SATISFIED_BY",
    }

    assert relationship_record_to_dict(record) == {
        "source": "node-1",
        "target": "node-2",
        "type": "SATISFIED_BY",
        "weight": 0.9,
        "description": "links requirement to deliverable",
        "keywords": "SATISFIED_BY",
    }


def test_type_and_count_helpers_read_neo4j_row_shapes() -> None:
    assert type_counts_from_records(
        [
            {"type": "requirement", "count": 2},
            {"type": "deliverable", "count": 1},
        ]
    ) == {"requirement": 2, "deliverable": 1}
    assert entity_names_from_records(
        [{"entity_name": "REQ-1"}, {"entity_name": "DEL-1"}]
    ) == ["REQ-1", "DEL-1"]
    assert count_from_record({"created_count": 4}, "created_count") == 4
    assert count_from_record(None, "created_count") == 0


def test_partition_entities_by_name_rejects_missing_names() -> None:
    valid, rejected = partition_entities_by_name(
        [
            {"entity_name": "REQ-1", "entity_type": "requirement"},
            {"entity_name": "", "entity_type": "requirement"},
            {"entity_type": "deliverable"},
        ]
    )

    assert valid == [{"entity_name": "REQ-1", "entity_type": "requirement"}]
    assert [item["entity_type"] for item in rejected] == ["requirement", "deliverable"]


def test_group_entities_by_type_lowercases_and_handles_missing_type() -> None:
    grouped = group_entities_by_type(
        [
            {"entity_name": "REQ-1", "entity_type": "Requirement"},
            {"entity_name": "REQ-2", "entity_type": "requirement"},
            {"entity_name": "UNKNOWN"},
        ]
    )

    assert [item["entity_name"] for item in grouped["requirement"]] == ["REQ-1", "REQ-2"]
    assert grouped[""] == [{"entity_name": "UNKNOWN"}]
