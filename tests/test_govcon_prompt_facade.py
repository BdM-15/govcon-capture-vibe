from prompts.govcon import EXTRACTION_PROMPTS, QUERY_PROMPTS
from prompts.govcon_prompt import GOVCON_PROMPTS, _build_v8_system_prompt


def test_govcon_prompt_facade_merges_internal_slices() -> None:
    assert GOVCON_PROMPTS == {**EXTRACTION_PROMPTS, **QUERY_PROMPTS}


def test_govcon_prompt_facade_keeps_legacy_builder_contract() -> None:
    assert GOVCON_PROMPTS["entity_extraction_json_system_prompt"] == _build_v8_system_prompt()
