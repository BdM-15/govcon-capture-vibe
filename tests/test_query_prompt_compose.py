"""Tests for LightRAG + GovCon composed query prompts."""

from prompts.govcon.query import QUERY_PROMPTS
from prompts.govcon.query_compose import compose_govcon_rag_response, lightrag_query_prompts


def test_rag_response_preserves_lightrag_formatting_spine() -> None:
    prompt = QUERY_PROMPTS["rag_response"]
    assert "3. Formatting & Language:" in prompt
    assert "headings, bold text, bullet points" in prompt
    assert "{response_type}" in prompt
    assert "4. References Section Format:" in prompt
    assert "### References" in prompt
    assert "6. Additional Instructions: {user_prompt}" in prompt
    assert "{context_data}" in prompt


def test_naive_rag_response_preserves_lightrag_formatting_spine() -> None:
    prompt = QUERY_PROMPTS["naive_rag_response"]
    assert "3. Formatting & Language:" in prompt
    assert "{content_data}" in prompt


def test_rag_response_includes_govcon_domain_blocks_only() -> None:
    prompt = QUERY_PROMPTS["rag_response"]
    assert "Theseus Scope" in prompt
    assert "Solicitation Format Awareness" in prompt
    assert "Ontology vs Fact" in prompt
    assert "do not append follow-up question lists" in prompt.lower()
    assert "---GovCon Output Discipline" not in prompt
    assert "---Response Contract (apply now)---" not in prompt
    assert "**Structure (MANDATORY):**" not in prompt
    assert "**CRITICAL:** Every grounded answer MUST include inline `[N]`" not in prompt


def test_rag_response_drops_conflicting_format_overrides() -> None:
    prompt = QUERY_PROMPTS["rag_response"]
    assert "not one-line bullets" not in prompt
    assert "expand only as much as the tier requires" not in prompt
    assert "Response Depth tiers" not in prompt


def test_compose_keeps_lightrag_tail_after_govcon_injection() -> None:
    base = lightrag_query_prompts()["rag_response"]
    composed = compose_govcon_rag_response(
        base,
        govcon_preamble="---Role---\nTest role",
        goal_block="---Goal---\nTest goal",
        step_addendum="\n  - Extra rule",
    )
    assert "Test role" in composed
    assert "Extra rule" in composed
    assert "3. Formatting & Language:" in composed
    assert composed.index("3. Formatting & Language:") < composed.index("---Context---")
    assert composed.rstrip().endswith("{context_data}")