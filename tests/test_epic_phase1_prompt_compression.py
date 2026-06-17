"""Phase 1 epic: prompt dedup + compaction (zero extra LLM calls per chunk)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from prompts.govcon.extraction import EXTRACTION_PROMPTS
from src.extraction.govcon_chunking import FOCUS_PREFIX, decorate_govcon_chunks
from src.ontology.entity_catalog import get_default_catalog

_MAX_COMPACT_GUIDANCE_CHARS = 6500


def test_user_prompt_has_no_duplicate_entity_types_guidance() -> None:
    user_prompt = EXTRACTION_PROMPTS["entity_extraction_json_user_prompt"]
    assert "{entity_types_guidance}" not in user_prompt
    assert "---Entity Types---" not in user_prompt


def test_system_prompt_still_has_entity_types_guidance_placeholder() -> None:
    system_prompt = EXTRACTION_PROMPTS["entity_extraction_json_system_prompt"]
    assert "{entity_types_guidance}" in system_prompt


def test_compact_extraction_guidance_under_budget_and_lists_all_types() -> None:
    catalog = get_default_catalog()
    compact = catalog.render_extraction_guidance()

    assert len(compact) < _MAX_COMPACT_GUIDANCE_CHARS
    assert "GOVCON ENTITY TYPE INDEX" in compact
    assert "TOP DISAMBIGUATION" in compact

    for name in sorted(catalog.entity_type_names):
        assert f". {name} —" in compact, f"missing index line for {name}"

    part_d = catalog.render_part_d()
    assert len(compact) < len(part_d) // 2


def test_govcon_yaml_has_three_examples() -> None:
    path = Path(__file__).resolve().parents[1] / "prompts" / "entity_type" / "govcon.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    examples = data["entity_extraction_json_examples"]
    assert len(examples) == 3
    joined = "\n".join(examples)
    assert "EXAMPLE 1" in joined and "L↔M" in joined
    assert "EXAMPLE 2" in joined and "workload_metric" in joined
    assert "EXAMPLE 3" in joined and "ANTI-PATTERN" in joined


def test_chunk_banner_includes_extract_focus_for_classified_docs() -> None:
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
    assert "evaluation_factor" in content
    assert "proposal_instruction" in content
    assert "mandatory CHILD_OF" in content


def test_prompt_budget_user_smaller_without_part_d_dup() -> None:
    user_prompt = EXTRACTION_PROMPTS["entity_extraction_json_user_prompt"]
    # Prior user prompt carried a second full Part D injection (~26K tokens wasted).
    assert len(user_prompt) < 2500
    assert user_prompt.count("entity_types_guidance") == 0