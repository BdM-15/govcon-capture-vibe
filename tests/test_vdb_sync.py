from src.inference.vdb_sync import _build_sync_audit


def test_build_sync_audit_counts_duplicate_pairs_and_direct_overlap() -> None:
    relationships = [
        {"source_name": "A", "target_name": "B", "relationship_type": "REFERENCES"},
        {"source_name": "B", "target_name": "A", "relationship_type": "REFERENCES"},
        {"source_name": "C", "target_name": "D", "relationship_type": "CHILD_OF"},
    ]

    audit = _build_sync_audit(
        relationships,
        directed_pairs={("A", "B"), ("C", "D")},
    )

    assert audit == {
        "inferred_relationship_count": 3,
        "unique_pair_count": 2,
        "duplicate_pair_count": 1,
        "overlapping_directed_pair_count": 2,
        "estimated_new_vdb_pair_count": 0,
    }


def test_build_sync_audit_handles_missing_direct_pair_context() -> None:
    relationships = [
        {"source_name": "A", "target_name": "B", "relationship_type": "REFERENCES"},
        {"source_name": "C", "target_name": "D", "relationship_type": "CHILD_OF"},
    ]

    audit = _build_sync_audit(relationships)

    assert audit == {
        "inferred_relationship_count": 2,
        "unique_pair_count": 2,
        "duplicate_pair_count": 0,
        "overlapping_directed_pair_count": None,
        "estimated_new_vdb_pair_count": None,
    }