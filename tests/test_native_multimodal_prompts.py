from prompts.multimodal.govcon_multimodal_prompts import GOVCON_NATIVE_MULTIMODAL_PROMPTS


def test_native_multimodal_prompts_match_lightrag_contract() -> None:
    assert set(GOVCON_NATIVE_MULTIMODAL_PROMPTS) == {
        "image_analysis",
        "table_analysis",
        "equation_analysis",
    }

    table_prompt = GOVCON_NATIVE_MULTIMODAL_PROMPTS["table_analysis"]
    image_prompt = GOVCON_NATIVE_MULTIMODAL_PROMPTS["image_analysis"]
    equation_prompt = GOVCON_NATIVE_MULTIMODAL_PROMPTS["equation_analysis"]

    for prompt in (table_prompt, image_prompt, equation_prompt):
        assert "{language}" in prompt
        assert '"name"' in prompt
        assert '"description"' in prompt
        assert "entity_info" not in prompt
        assert "detailed_description" not in prompt
        assert "REQUIREMENT" in prompt
        assert "EVALUATION_FACTOR" in prompt

    assert '"type"' in image_prompt
    assert "Photo, Illustration, Screenshot, Icon, Chart, Table" in image_prompt
    assert '"equation"' in equation_prompt
    assert "================ TABLE CONTENT ================" in table_prompt
    assert "================ EQUATION BODY ================" in equation_prompt


def test_native_multimodal_prompts_format_with_lightrag_variables() -> None:
    variables = {
        "language": "English",
        "content": "A | B\n1 | 2",
        "captions": "n/a",
        "footnotes": "n/a",
        "leading": "Section M",
        "trailing": "End of table",
        "item_id": "table-1",
        "file_path": "sample.pdf",
    }

    for prompt in GOVCON_NATIVE_MULTIMODAL_PROMPTS.values():
        rendered = prompt.format(**variables)
        assert "sample.pdf" in rendered
        assert '"name"' in rendered
        assert "Output:" in rendered