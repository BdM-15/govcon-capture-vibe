from src.inference.neo4j_graph_io import (
    group_retype_updates,
    partition_relationships_by_type,
)


def test_partition_relationships_rejects_missing_or_blank_types() -> None:
    valid, rejected = partition_relationships_by_type(
        [
            {"relationship_type": "SATISFIES", "source_id": "a"},
            {"relationship_type": "   ", "source_id": "b"},
            {"relationship_type": None, "source_id": "c"},
            {"source_id": "d"},
        ]
    )

    assert valid == [{"relationship_type": "SATISFIES", "source_id": "a"}]
    assert [item["source_id"] for item in rejected] == ["b", "c", "d"]


def test_group_retype_updates_batches_by_old_and_new_type() -> None:
    updates = [
        {
            "source_id": "a",
            "target_id": "b",
            "old_type": "RELATED",
            "new_type": "SATISFIES",
        },
        {
            "source_id": "c",
            "target_id": "d",
            "old_type": "RELATED",
            "new_type": "SATISFIES",
        },
        {
            "source_id": "e",
            "target_id": "f",
            "old_type": "LINKS_TO",
            "new_type": "EVALUATED_BY",
        },
    ]

    batches = group_retype_updates(updates)

    assert set(batches) == {
        ("RELATED", "SATISFIES"),
        ("LINKS_TO", "EVALUATED_BY"),
    }
    assert [item["source_id"] for item in batches[("RELATED", "SATISFIES")]] == [
        "a",
        "c",
    ]
    assert batches[("LINKS_TO", "EVALUATED_BY")][0]["target_id"] == "f"
