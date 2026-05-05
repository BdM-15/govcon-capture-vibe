from src.server.rag_post_init import (
    activate_govcon_multimodal_prompts,
    apply_lightrag_govcon_prompts,
)


class _Logger:
    def __init__(self):
        self.messages = []

    def info(self, message, *args):
        self.messages.append(message % args if args else message)


def test_apply_lightrag_govcon_prompts_updates_target_map() -> None:
    logger = _Logger()
    prompt_map = {"existing": 1}

    apply_lightrag_govcon_prompts(
        prompt_map=prompt_map,
        govcon_prompts={
            "entity_extraction_json_system_prompt": "abc",
            "keywords_extraction_examples": [1, 2],
        },
        log=logger,
    )

    assert prompt_map["entity_extraction_json_system_prompt"] == "abc"
    assert any("REPLACED LightRAG prompt system" in message for message in logger.messages)


def test_activate_govcon_multimodal_prompts_registers_and_activates_language() -> None:
    logger = _Logger()
    calls = []

    activate_govcon_multimodal_prompts(
        multimodal_prompts={"a": 1, "b": 2},
        register_prompt_language_func=lambda name, prompts: calls.append(("register", name, prompts)),
        set_prompt_language_func=lambda name: calls.append(("set", name)),
        log=logger,
    )

    assert calls == [
        ("register", "govcon", {"a": 1, "b": 2}),
        ("set", "govcon"),
    ]
    assert any("Registered and activated 'govcon' prompt language" in message for message in logger.messages)