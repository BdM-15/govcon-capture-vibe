"""Option A + C-lite: hierarchy prompt hardening and structural PP linking."""

from __future__ import annotations

from pathlib import Path

import yaml

from prompts.govcon.extraction import EXTRACTION_PROMPTS
from src.extraction.govcon_chunking import FOCUS_PREFIX, decorate_govcon_chunks, render_focus_paragraph
from src.inference.algorithms.infer_document_structure import infer_document_structure
from src.ontology.entity_catalog import get_default_catalog

_MAX_COMPACT_GUIDANCE_CHARS = 6500


def test_structural_containment_in_compact_guidance() -> None:
    compact = get_default_catalog().render_extraction_guidance()
    assert "STRUCTURAL CONTAINMENT (mandatory)" in compact
    assert len(compact) < _MAX_COMPACT_GUIDANCE_CHARS


def test_system_prompt_mandatory_hierarchy_rules() -> None:
    system_prompt = EXTRACTION_PROMPTS["entity_extraction_json_system_prompt"]
    assert "HIERARCHY RULE (mandatory for structural types)" in system_prompt
    assert "floating without a containment parent" in system_prompt
    assert "work_scope_item) have CHILD_OF" in system_prompt


def test_example_one_teaches_section_child_of_chain() -> None:
    path = Path(__file__).resolve().parents[1] / "prompts" / "entity_type" / "govcon.yaml"
    examples = yaml.safe_load(path.read_text(encoding="utf-8"))["entity_extraction_json_examples"]
    example_one = examples[0]
    assert "document_section" in example_one
    assert '"CHILD_OF, section containment"' in example_one
    assert "Section M Evaluation Factors" in example_one


def test_solicitation_focus_requires_mandatory_child_of() -> None:
    focus = render_focus_paragraph("solicitation")
    assert "mandatory CHILD_OF" in focus
    assert "no orphan structural" in focus
    assert "table row/cell IDs" in focus


def test_infer_document_structure_links_factor_to_section() -> None:
    section = {
        "id": "sec-m",
        "entity_name": "Section M Evaluation Factors",
        "entity_type": "document_section",
        "description": "Section M scoring criteria.",
    }
    factor = {
        "id": "fac-1",
        "entity_name": "Factor 1 Technical Approach",
        "entity_type": "evaluation_factor",
        "description": "Factor 1: Technical Approach (40%). Section M evaluation criterion.",
    }
    entities = [section, factor]
    entities_by_type = {
        "document_section": [section],
        "evaluation_factor": [factor],
        "document": [],
        "deliverable": [],
        "requirement": [],
    }

    rels = infer_document_structure(entities, entities_by_type)
    child_of = [
        r for r in rels
        if r["relationship_type"] == "CHILD_OF" and r["source_id"] == "fac-1"
    ]
    assert any(r["target_id"] == "sec-m" for r in child_of)


def test_infer_document_structure_links_subfactor_to_parent_factor() -> None:
    parent = {
        "id": "fac-1",
        "entity_name": "Factor 1 Technical Approach",
        "entity_type": "evaluation_factor",
        "description": "Top-level factor.",
    }
    child = {
        "id": "sub-1",
        "entity_name": "Subfactor 1.2 Staffing Approach",
        "entity_type": "evaluation_factor",
        "description": "Subfactor under Factor 1.",
    }
    entities = [parent, child]
    entities_by_type = {
        "evaluation_factor": [parent, child],
        "document_section": [],
        "document": [],
        "deliverable": [],
        "requirement": [],
    }

    rels = infer_document_structure(entities, entities_by_type)
    assert any(
        r["relationship_type"] == "CHILD_OF"
        and r["source_id"] == "sub-1"
        and r["target_id"] == "fac-1"
        for r in rels
    )


def test_chunk_banner_still_classifies_solicitation() -> None:
    source = (
        "Request for Proposal\n"
        "Section L Instructions to Offerors\n"
        "Section M Evaluation Factors"
    )
    chunks = [{"content": source, "chunk_order_index": 0}]
    decorated = decorate_govcon_chunks(chunks, source_content=source)
    content = decorated[0]["content"]
    assert content.startswith("[GOVCON_DOC: type=solicitation;")
    assert FOCUS_PREFIX in content