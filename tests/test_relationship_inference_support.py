from src.inference.relationship_inference_support import (
    apply_canonical_mapping,
    apply_type_based_heuristics,
    build_deduplication_prompt,
    find_potential_duplicate_pairs,
    normalize_entity_name,
)


def test_normalize_entity_name_collapses_subfactor_punctuation_variants() -> None:
    assert normalize_entity_name("Subfactor 4: Small Business Participation") == normalize_entity_name(
        "Subfactor 4 Small Business Participation"
    )
    assert normalize_entity_name("Subfactor 3: Key Personnel") == normalize_entity_name(
        "Subfactor 3 Key Personnel"
    )


def test_find_potential_duplicate_pairs_checks_evaluation_factors() -> None:
    grouped = {
        "evaluation_factor": [
            {"entity_name": "Subfactor 4: Small Business Participation", "entity_type": "evaluation_factor"},
            {"entity_name": "Subfactor 4 Small Business Participation", "entity_type": "evaluation_factor"},
        ]
    }

    duplicates = find_potential_duplicate_pairs(grouped)

    assert "evaluation_factor" in duplicates
    assert duplicates["evaluation_factor"] == [
        (
            {"entity_name": "Subfactor 4: Small Business Participation", "entity_type": "evaluation_factor"},
            {"entity_name": "Subfactor 4 Small Business Participation", "entity_type": "evaluation_factor"},
        )
    ]


def test_find_potential_duplicate_pairs_flags_section_variants() -> None:
    grouped = {
        "section": [
            {"entity_name": "SECTION C.4", "entity_type": "section"},
            {"entity_name": "Section C4", "entity_type": "section"},
            {"entity_name": "Section L", "entity_type": "section"},
        ]
    }

    pairs = find_potential_duplicate_pairs(grouped)

    assert "section" in pairs
    assert len(pairs["section"]) == 1
    prompt = build_deduplication_prompt(pairs["section"])
    assert "ENTITY PAIRS TO EVALUATE" in prompt
    assert "SECTION C.4" in prompt


def test_apply_canonical_mapping_rewrites_edges() -> None:
    nodes = [
        {"id": "1", "entity_name": "section c.4", "entity_type": "section", "description": "lower"},
        {"id": "2", "entity_name": "Requirement 1", "entity_type": "requirement", "description": "req"},
    ]
    edges = [{"source": "Requirement 1", "target": "section c.4"}]

    deduped_nodes, updated_edges = apply_canonical_mapping(
        nodes,
        edges,
        {"section c.4": "Section C.4 - Supply"},
    )

    assert deduped_nodes[0]["entity_name"] == "Section C.4 - Supply"
    assert updated_edges == [{"source": "Requirement 1", "target": "Section C.4 - Supply"}]


def test_apply_type_based_heuristics_links_sections_and_attachment_sow() -> None:
    grouped = {
        "section": [
            {"id": "sec-c", "entity_name": "Section C"},
            {"id": "sec-j", "entity_name": "Section J"},
            {"id": "sec-l", "entity_name": "Section L"},
        ],
        "deliverable": [{"id": "del-1", "entity_name": "CDRL A001"}],
        "submission_instruction": [{"id": "ins-1", "entity_name": "Volume I Instructions"}],
        "statement_of_work": [
            {"id": "sow-1", "entity_name": "Attachment J-1 PWS"},
            {"id": "sow-2", "entity_name": "Base SOW"},
        ],
    }
    existing_edges = [{"source": "del-1", "target": "sec-j"}]

    rels = apply_type_based_heuristics(grouped, existing_edges)

    assert {rel["source_id"] for rel in rels} == {"ins-1", "sow-1", "sow-2"}
    assert any(rel["source_id"] == "sow-1" and rel["target_id"] == "sec-j" for rel in rels)
    assert any(rel["source_id"] == "sow-2" and rel["target_id"] == "sec-c" for rel in rels)