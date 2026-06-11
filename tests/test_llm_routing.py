import asyncio
from types import SimpleNamespace

from src.server import llm_routing


class _Settings:
    extraction_llm_name = "extract-model"
    reasoning_llm_name = "reason-model"
    keyword_llm_name = "keyword-model"
    vlm_llm_name = "vlm-model"
    llm_max_output_tokens = 12345
    llm_timeout = 600
    keyword_uses_ollama = False
    ollama_openai_base_url = "http://localhost:11434/v1"


def test_build_role_llm_routing_prompt_only(monkeypatch) -> None:
    monkeypatch.delenv("ENTITY_EXTRACTION_STRICT_SCHEMA", raising=False)
    routing = llm_routing.build_role_llm_routing(
        _Settings(),
        xai_api_key="key",
        xai_base_url="https://api.example.com",
    )

    assert routing.use_strict_schema is False
    assert set(routing.role_llm_configs.keys()) == {"extract", "query", "keyword", "vlm"}
    assert routing.role_llm_configs["extract"].kwargs == {"max_tokens": llm_routing.EXTRACT_MAX_TOKENS}
    assert routing.role_llm_configs["extract"].metadata["model"] == "extract-model"
    assert routing.role_llm_configs["query"].metadata["model"] == "reason-model"
    assert routing.role_llm_configs["keyword"].metadata["model"] == "keyword-model"
    assert routing.role_llm_configs["vlm"].metadata["model"] == "vlm-model"


def test_extract_role_overrides_response_format_in_strict_mode(monkeypatch) -> None:
    calls = []
    monkeypatch.setenv("ENTITY_EXTRACTION_STRICT_SCHEMA", "true")
    monkeypatch.setattr(
        llm_routing,
        "build_response_format",
        lambda: {"type": "json_schema", "json_schema": {"name": "GovConExtractionResult", "schema": {"properties": {"entities": {"items": {"properties": {"type": {"enum": ["a", "b"]}}}}, "additionalProperties": False}}}},
    )

    async def fake_complete(model, prompt, **kwargs):
        calls.append((model, prompt, kwargs))
        return {"ok": True}

    monkeypatch.setattr(llm_routing, "openai_complete_if_cache", fake_complete)
    routing = llm_routing.build_role_llm_routing(
        _Settings(),
        xai_api_key="key",
        xai_base_url="https://api.example.com",
    )

    asyncio.run(
        routing.role_llm_configs["extract"].func(
            "prompt",
            response_format={"type": "json_object"},
        )
    )

    assert calls[0][0] == "extract-model"
    assert calls[0][2]["response_format"]["type"] == "json_schema"
    assert routing.role_llm_configs["extract"].metadata["host"].endswith("#strict-jsonschema")


def test_native_multimodal_extract_role_keeps_json_object_boundary(monkeypatch) -> None:
    calls = []
    monkeypatch.setenv("ENTITY_EXTRACTION_STRICT_SCHEMA", "true")
    monkeypatch.setattr(
        llm_routing,
        "build_response_format",
        lambda: {"type": "json_schema", "json_schema": {"name": "GovConExtractionResult", "schema": {"properties": {"entities": {"items": {"properties": {"type": {"enum": ["a", "b"]}}}}, "additionalProperties": False}}}},
    )

    async def fake_complete(model, prompt, **kwargs):
        calls.append((model, prompt, kwargs))
        return {"ok": True}

    monkeypatch.setattr(llm_routing, "openai_complete_if_cache", fake_complete)
    routing = llm_routing.build_role_llm_routing(
        _Settings(),
        xai_api_key="key",
        xai_base_url="https://api.example.com",
    )

    for prompt in (
        "You are an expert federal acquisition table analyzer.\n================ TABLE CONTENT ================",
        "You are an expert federal acquisition quantitative analyst.\n================ EQUATION BODY ================",
    ):
        asyncio.run(
            routing.role_llm_configs["extract"].func(
                prompt,
                response_format={"type": "json_object"},
            )
        )

    assert [call[0] for call in calls] == ["vlm-model", "vlm-model"]
    assert [call[2]["response_format"] for call in calls] == [
        {"type": "json_object"},
        {"type": "json_object"},
    ]


def test_modal_llm_drops_govcon_extraction_schema(monkeypatch) -> None:
    calls = []
    monkeypatch.delenv("ENTITY_EXTRACTION_STRICT_SCHEMA", raising=False)

    async def fake_complete(model, prompt, **kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(llm_routing, "openai_complete_if_cache", fake_complete)
    routing = llm_routing.build_role_llm_routing(
        _Settings(),
        xai_api_key="key",
        xai_base_url="https://api.example.com",
    )

    asyncio.run(
        routing.modal_llm_func(
            "prompt",
            response_format={"json_schema": {"name": "GovConExtractionResult"}},
        )
    )

    assert "response_format" not in calls[0]
    assert calls[0]["max_tokens"] == llm_routing.VLM_MAX_TOKENS


def test_vlm_llm_builds_image_message(monkeypatch) -> None:
    calls = []
    monkeypatch.delenv("ENTITY_EXTRACTION_STRICT_SCHEMA", raising=False)

    async def fake_complete(model, prompt, **kwargs):
        calls.append((model, prompt, kwargs))
        return {"ok": True}

    monkeypatch.setattr(llm_routing, "openai_complete_if_cache", fake_complete)
    routing = llm_routing.build_role_llm_routing(
        _Settings(),
        xai_api_key="key",
        xai_base_url="https://api.example.com",
    )

    asyncio.run(routing.vision_model_func("see this", system_prompt="sys", image_data="abc"))

    assert calls[0][0] == "vlm-model"
    messages = calls[0][2]["messages"]
    assert messages[0] == {"role": "system", "content": "sys"}
    assert messages[1]["content"][1]["image_url"]["url"] == "data:image/jpeg;base64,abc"


def test_keyword_role_routes_to_ollama_when_binding_enabled(monkeypatch) -> None:
    calls = []
    monkeypatch.delenv("ENTITY_EXTRACTION_STRICT_SCHEMA", raising=False)

    async def fake_complete(model, prompt, **kwargs):
        calls.append((model, kwargs.get("base_url"), kwargs.get("api_key")))
        return {"ok": True}

    monkeypatch.setattr(llm_routing, "openai_complete_if_cache", fake_complete)
    settings = _Settings()
    settings.keyword_uses_ollama = True
    settings.keyword_llm_name = "qwen2.5:7b-instruct"
    routing = llm_routing.build_role_llm_routing(
        settings,
        xai_api_key="xai-key",
        xai_base_url="https://api.x.ai/v1",
    )

    asyncio.run(routing.role_llm_configs["keyword"].func("keywords please"))

    assert calls == [("qwen2.5:7b-instruct", "http://localhost:11434/v1", "ollama")]
    assert routing.role_llm_configs["keyword"].metadata == {
        "model": "qwen2.5:7b-instruct",
        "host": "http://localhost:11434/v1",
        "binding": "openai-compat",
    }