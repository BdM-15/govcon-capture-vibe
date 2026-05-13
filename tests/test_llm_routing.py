import asyncio
from types import SimpleNamespace

from src.server import llm_routing


class _Settings:
    extraction_llm_name = "extract-model"
    reasoning_llm_name = "reason-model"
    llm_max_output_tokens = 12345
    llm_timeout = 600
    vault_curation_llm_model = "qwen3.5:9b"
    vault_curation_llm_host = "http://localhost:11434/v1"


def test_build_role_llm_routing_prompt_only(monkeypatch) -> None:
    monkeypatch.delenv("ENTITY_EXTRACTION_STRICT_SCHEMA", raising=False)
    routing = llm_routing.build_role_llm_routing(
        _Settings(),
        xai_api_key="key",
        xai_base_url="https://api.example.com",
    )

    assert routing.use_strict_schema is False
    # vault_curation is NOT a LightRAG role — must not appear in role_llm_configs
    assert set(routing.role_llm_configs.keys()) == {"extract", "query", "keyword", "vlm"}
    assert routing.role_llm_configs["extract"].kwargs == {"max_tokens": llm_routing.EXTRACT_MAX_TOKENS}
    # vault_curation_func lives as a standalone callable on RoleLLMRouting
    assert callable(routing.vault_curation_func)


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

    messages = calls[0][2]["messages"]
    assert messages[0] == {"role": "system", "content": "sys"}
    assert messages[1]["content"][1]["image_url"]["url"] == "data:image/jpeg;base64,abc"