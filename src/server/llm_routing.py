"""Per-role LightRAG/RAG-Anything LLM routing setup."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from lightrag.lightrag import RoleLLMConfig
from lightrag.llm.openai import openai_complete_if_cache

from src.ontology.extraction_schema import build_response_format

logger = logging.getLogger(__name__)

EXTRACT_MAX_TOKENS = 32000
KEYWORD_MAX_TOKENS = 4096
VLM_MAX_TOKENS = 8000
QUERY_TIMEOUT = 900
KEYWORD_TIMEOUT = 60
VLM_TIMEOUT = 300


@dataclass
class RoleLLMRouting:
    llm_model_func: Callable[..., Awaitable[Any]]
    vision_model_func: Callable[..., Awaitable[Any]]
    modal_llm_func: Callable[..., Awaitable[Any]]
    role_llm_configs: dict[str, RoleLLMConfig]
    use_strict_schema: bool


def _strict_schema_enabled() -> bool:
    return os.environ.get("ENTITY_EXTRACTION_STRICT_SCHEMA", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def build_role_llm_routing(settings, *, xai_api_key: str, xai_base_url: str) -> RoleLLMRouting:
    """Build all per-role LLM wrappers/configs used by LightRAG and RAG-Anything."""
    extraction_model = settings.extraction_llm_name
    reasoning_model = settings.reasoning_llm_name
    query_max_tokens = settings.llm_max_output_tokens
    extract_timeout = settings.llm_timeout

    use_strict_schema = _strict_schema_enabled()
    strict_extraction_response_format = None
    if use_strict_schema:
        strict_extraction_response_format = build_response_format()
        strict_schema = strict_extraction_response_format["json_schema"]["schema"]
        strict_entity_types = strict_schema["properties"]["entities"]["items"]["properties"]["type"]["enum"]
        logger.info("=" * 88)
        logger.info("✅ STRICT JSON SCHEMA STARTUP CHECK: ENABLED")
        logger.info(
            "   ENTITY_EXTRACTION_STRICT_SCHEMA=%s",
            os.environ.get("ENTITY_EXTRACTION_STRICT_SCHEMA"),
        )
        logger.info(
            "   response_format=%s | schema=%s | entity_type_enum=%d | additionalProperties=%s",
            strict_extraction_response_format.get("type"),
            strict_extraction_response_format["json_schema"].get("name"),
            len(strict_entity_types),
            strict_schema.get("additionalProperties"),
        )
        logger.info(
            "   extract role will override LightRAG JSON-mode response_format={type: json_object} at provider boundary"
        )
        logger.info("   extract cache identity marker: host suffix #strict-jsonschema")
        logger.info("=" * 88)
    else:
        logger.warning("=" * 88)
        logger.warning("⚠️  STRICT JSON SCHEMA STARTUP CHECK: DISABLED")
        logger.warning(
            "   ENTITY_EXTRACTION_STRICT_SCHEMA=%s",
            os.environ.get("ENTITY_EXTRACTION_STRICT_SCHEMA"),
        )
        logger.warning("   Extraction will run in prompt-only JSON mode")
        logger.warning("=" * 88)

    async def extract_llm_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        kwargs.setdefault("max_tokens", EXTRACT_MAX_TOKENS)
        if strict_extraction_response_format is not None:
            kwargs["response_format"] = strict_extraction_response_format
        return await openai_complete_if_cache(
            extraction_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=xai_api_key,
            base_url=xai_base_url,
            **kwargs,
        )

    async def query_llm_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        kwargs.setdefault("max_tokens", query_max_tokens)
        return await openai_complete_if_cache(
            reasoning_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=xai_api_key,
            base_url=xai_base_url,
            **kwargs,
        )

    async def keyword_llm_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        kwargs["max_tokens"] = KEYWORD_MAX_TOKENS
        return await openai_complete_if_cache(
            extraction_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=xai_api_key,
            base_url=xai_base_url,
            **kwargs,
        )

    async def vlm_llm_func(prompt, system_prompt=None, history_messages=[], image_data=None, messages=None, **kwargs):
        kwargs.setdefault("max_tokens", VLM_MAX_TOKENS)
        if messages:
            return await openai_complete_if_cache(
                extraction_model,
                "",
                system_prompt=None,
                history_messages=[],
                messages=messages,
                api_key=xai_api_key,
                base_url=xai_base_url,
                **kwargs,
            )
        if image_data:
            built_messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                    ],
                }
            ]
            if system_prompt:
                built_messages.insert(0, {"role": "system", "content": system_prompt})
            return await openai_complete_if_cache(
                extraction_model,
                "",
                system_prompt=None,
                history_messages=[],
                messages=built_messages,
                api_key=xai_api_key,
                base_url=xai_base_url,
                **kwargs,
            )
        return await openai_complete_if_cache(
            extraction_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=xai_api_key,
            base_url=xai_base_url,
            **kwargs,
        )

    async def modal_llm_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        kwargs.setdefault("max_tokens", VLM_MAX_TOKENS)
        response_format = kwargs.get("response_format") or {}
        json_schema = response_format.get("json_schema") if isinstance(response_format, dict) else None
        if isinstance(json_schema, dict) and json_schema.get("name") == "GovConExtractionResult":
            kwargs.pop("response_format", None)
        return await openai_complete_if_cache(
            extraction_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=xai_api_key,
            base_url=xai_base_url,
            **kwargs,
        )

    logger.info("✅ Native LightRAG 1.5.0 role_llm_configs routing enabled")
    extract_mode_label = "JSON strict schema" if use_strict_schema else "JSON prompt-only"
    logger.info(
        "   extract  → %s  max_tokens=%6d  timeout=%ss  (%s)",
        f"{extraction_model:40s}",
        EXTRACT_MAX_TOKENS,
        extract_timeout,
        extract_mode_label,
    )
    logger.info(
        "   query    → %s  max_tokens=%6d  timeout=%ss",
        f"{reasoning_model:40s}",
        query_max_tokens,
        QUERY_TIMEOUT,
    )
    logger.info(
        "   keyword  → %s  max_tokens=%6d  timeout=%ss",
        f"{extraction_model:40s}",
        KEYWORD_MAX_TOKENS,
        KEYWORD_TIMEOUT,
    )
    logger.info(
        "   vlm      → %s  max_tokens=%6d  timeout=%ss",
        f"{extraction_model:40s}",
        VLM_MAX_TOKENS,
        VLM_TIMEOUT,
    )

    extract_kwargs: dict[str, Any] = {"max_tokens": EXTRACT_MAX_TOKENS}
    if use_strict_schema:
        extract_kwargs["response_format"] = strict_extraction_response_format
        logger.info("✅ Strict JSON schema enforcement ENABLED for `extract` role (xAI json_schema strict=true)")
    else:
        logger.info(
            "ℹ️  Strict JSON schema NOT enabled — using prompt-only JSON mode (set ENTITY_EXTRACTION_STRICT_SCHEMA=true to enforce)"
        )

    extract_metadata = {"model": extraction_model, "host": xai_base_url, "binding": "openai"}
    if use_strict_schema:
        extract_metadata["host"] = f"{xai_base_url}#strict-jsonschema"

    role_llm_configs = {
        "extract": RoleLLMConfig(
            func=extract_llm_func,
            kwargs=extract_kwargs,
            timeout=extract_timeout,
            metadata=extract_metadata,
        ),
        "query": RoleLLMConfig(
            func=query_llm_func,
            kwargs={"max_tokens": query_max_tokens},
            timeout=QUERY_TIMEOUT,
            metadata={"model": reasoning_model, "host": xai_base_url, "binding": "openai"},
        ),
        "keyword": RoleLLMConfig(
            func=keyword_llm_func,
            kwargs={"max_tokens": KEYWORD_MAX_TOKENS},
            timeout=KEYWORD_TIMEOUT,
            metadata={"model": extraction_model, "host": xai_base_url, "binding": "openai"},
        ),
        "vlm": RoleLLMConfig(
            func=vlm_llm_func,
            kwargs={"max_tokens": VLM_MAX_TOKENS},
            timeout=VLM_TIMEOUT,
            metadata={"model": extraction_model, "host": xai_base_url, "binding": "openai"},
        ),
    }

    return RoleLLMRouting(
        llm_model_func=query_llm_func,
        vision_model_func=vlm_llm_func,
        modal_llm_func=modal_llm_func,
        role_llm_configs=role_llm_configs,
        use_strict_schema=use_strict_schema,
    )