import json

from src.inference.semantic_post_process_support import (
    apply_entity_name_updates_to_vdb,
    build_post_processing_result,
    canonicalize_factor_like_name,
    collect_relationship_retype_updates,
    count_vdb_entries,
    heuristic_table_type_mapping,
    plan_entity_name_updates,
    plan_entity_type_updates,
    resolve_generic_relationship,
    sync_entity_metadata_to_vdb,
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


def test_heuristic_table_type_mapping_prefers_section_l_instruction_tables() -> None:
    assert heuristic_table_type_mapping(
        {
            "entity_name": "Volume II Page Allocations Table (table)",
            "description": (
                "Section L.1.3 defines Volume II Technical Proposal 130-page limit allocation "
                "for Subfactor 1, 2, 3, and 4. Noncompliance risks unacceptable proposal."
            ),
        }
    ) == "proposal_instruction"

    assert heuristic_table_type_mapping(
        {
            "entity_name": "Small Business Subcontracting Goals Table (table)",
            "description": (
                "Section L.2.3 submission table for SBPCD and subcontracting goals under Instructions to Offerors."
            ),
        }
    ) == "proposal_instruction"


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


def test_sync_entity_metadata_to_vdb_matches_entity_id_when_vdb_uses_canonical_name(
    tmp_path,
) -> None:
    path = tmp_path / "vdb_entities.json"
    path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "entity_name": "Factor 1 Management",
                        "entity_type": None,
                        "description": None,
                        "source_id": "old-source",
                        "vector": [1.0],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    updated = sync_entity_metadata_to_vdb(
        str(tmp_path),
        [
            {
                "entity_id": "Factor 1 Management",
                "entity_name": None,
                "entity_type": "evaluation_factor",
                "description": "Management factor",
                "source_id": "chunk-abc",
            }
        ],
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    row = payload["data"][0]
    assert updated == 1
    assert row["entity_type"] == "evaluation_factor"
    assert row["description"] == "Management factor"
    assert row["source_id"] == "chunk-abc"


def test_sync_entity_metadata_to_vdb_updates_types_from_neo4j_snapshot(tmp_path) -> None:
    path = tmp_path / "vdb_entities.json"
    path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "entity_name": "Volume II Page Allocations Table (table)",
                        "entity_type": "table",
                        "description": "old",
                        "source_id": "old-source",
                        "vector": [1.0],
                    },
                    {
                        "entity_name": "Leave Alone",
                        "entity_type": "concept",
                        "description": "keep",
                        "source_id": "keep-source",
                        "vector": [2.0],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    updated = sync_entity_metadata_to_vdb(
        str(tmp_path),
        [
            {
                "entity_name": "Volume II Page Allocations Table (table)",
                "entity_type": "proposal_instruction",
                "description": "new",
                "source_id": "new-source",
            }
        ],
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["data"]
    assert updated == 1
    assert rows[0]["entity_type"] == "proposal_instruction"
    assert rows[0]["description"] == "new"
    assert rows[0]["source_id"] == "new-source"
    assert rows[1]["entity_type"] == "concept"


def test_canonicalize_factor_like_name_adds_expected_separator() -> None:
    assert canonicalize_factor_like_name("Subfactor 4 Small Business Participation") == (
        "Subfactor 4: Small Business Participation"
    )
    assert canonicalize_factor_like_name("Factor 2: Management Approach") == "Factor 2: Management Approach"


def test_plan_entity_name_updates_targets_evaluation_factor_duplicates() -> None:
    updates, mapping = plan_entity_name_updates(
        {
            "evaluation_factor": [
                {"id": "a", "entity_name": "Subfactor 4 Small Business Participation", "entity_type": "evaluation_factor"},
                {"id": "b", "entity_name": "Subfactor 4: Small Business Participation", "entity_type": "evaluation_factor"},
            ]
        }
    )

    assert updates == [
        {
            "id": "a",
            "new_entity_name": "Subfactor 4: Small Business Participation",
            "old_entity_name": "Subfactor 4 Small Business Participation",
        }
    ]
    assert mapping == {
        "Subfactor 4 Small Business Participation": "Subfactor 4: Small Business Participation"
    }


def test_apply_entity_name_updates_to_vdb_rewrites_entities_and_relationships(tmp_path) -> None:
    entity_path = tmp_path / "vdb_entities.json"
    relationship_path = tmp_path / "vdb_relationships.json"
    entity_path.write_text(
        json.dumps(
            {
                "data": [
                    {"entity_name": "Subfactor 4 Small Business Participation", "entity_type": "evaluation_factor"},
                    {"entity_name": "Other", "entity_type": "concept"},
                ]
            }
        ),
        encoding="utf-8",
    )
    relationship_path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "src_id": "Subfactor 4 Small Business Participation",
                        "tgt_id": "Section M",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    stats = apply_entity_name_updates_to_vdb(
        str(tmp_path),
        {"Subfactor 4 Small Business Participation": "Subfactor 4: Small Business Participation"},
    )

    entity_rows = json.loads(entity_path.read_text(encoding="utf-8"))["data"]
    relationship_rows = json.loads(relationship_path.read_text(encoding="utf-8"))["data"]
    assert stats == {"entities_updated": 1, "relationships_updated": 1}
    assert entity_rows[0]["entity_name"] == "Subfactor 4: Small Business Participation"
    assert relationship_rows[0]["src_id"] == "Subfactor 4: Small Business Participation"