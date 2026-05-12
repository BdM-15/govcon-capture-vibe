from src.ontology.govcon_kg import (
    build_ontology_stats,
    combine_knowledge_graph_parts,
    validate_custom_kg,
)


def test_combine_knowledge_graph_parts_merges_sections() -> None:
    kg = combine_knowledge_graph_parts(
        [
            ([{"entity_name": "A"}], [{"src_id": "A", "tgt_id": "B"}], [{"content": "c1"}]),
            ([{"entity_name": "B"}], [], [{"content": "c2"}]),
        ]
    )

    assert kg == {
        "entities": [{"entity_name": "A"}, {"entity_name": "B"}],
        "relationships": [{"src_id": "A", "tgt_id": "B"}],
        "chunks": [{"content": "c1"}, {"content": "c2"}],
    }


def test_build_ontology_stats_and_validation() -> None:
    stats = build_ontology_stats(
        {
            "shipley": ([{"entity_name": "A"}], [{"src_id": "A", "tgt_id": "B"}], [{"content": "c1"}]),
            "capture": ([{"entity_name": "B"}, {"entity_name": "C"}], [], []),
        }
    )
    assert stats["modules"]["shipley"] == {"entities": 1, "relationships": 1, "chunks": 1}
    assert stats["total_entities"] == 3
    assert stats["total_relationships"] == 1
    assert stats["total_chunks"] == 1

    is_valid, errors = validate_custom_kg(
        {
            "entities": [
                {"entity_name": "A", "entity_type": "concept", "description": "desc"},
                {"entity_name": "A", "entity_type": "concept", "description": "dup"},
            ],
            "relationships": [
                {"src_id": "A", "tgt_id": "Z", "description": "bad ref"},
                {"src_id": "", "tgt_id": "A", "description": "missing src"},
            ],
            "chunks": [{"content": ""}],
        }
    )
    assert is_valid is False
    assert "Duplicate entity name: A" in errors
    assert "Relationship 0: tgt_id 'Z' not found in entities" in errors
    assert "Relationship 1: missing src_id" in errors
    assert "Chunk 0: missing content" in errors