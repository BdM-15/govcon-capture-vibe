"""Helpers for single-pass LightRAG aquery_llm UI queries."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Callable

QueryLlmFunc = Callable[
    [str, str, list[dict], bool, dict],
    Any,
]


@dataclass(frozen=True)
class StreamQueryBundle:
    """Sources plus LLM output from one aquery_llm call."""

    sources_payload: dict | None
    result: str | AsyncIterator[str]
    is_streaming: bool


def sources_from_llm_result(result: dict[str, Any]) -> dict | None:
    """Project aquery_llm['data'] into the compact UI sources payload."""
    if not isinstance(result, dict) or result.get("status") != "success":
        return None
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    from src.server.chat_routes import trim_sources

    return trim_sources(data)


def stream_bundle_from_llm_result(result: dict[str, Any]) -> StreamQueryBundle:
    """Unpack an aquery_llm response into sources and streamable LLM output."""
    sources_payload = sources_from_llm_result(result)
    llm_response = result.get("llm_response") if isinstance(result, dict) else None
    if not isinstance(llm_response, dict):
        return StreamQueryBundle(
            sources_payload=sources_payload,
            result="",
            is_streaming=False,
        )

    if llm_response.get("is_streaming"):
        iterator = llm_response.get("response_iterator")
        if hasattr(iterator, "__aiter__"):
            return StreamQueryBundle(
                sources_payload=sources_payload,
                result=iterator,
                is_streaming=True,
            )
        return StreamQueryBundle(
            sources_payload=sources_payload,
            result="",
            is_streaming=False,
        )

    content = llm_response.get("content")
    return StreamQueryBundle(
        sources_payload=sources_payload,
        result="" if content is None else str(content),
        is_streaming=False,
    )


__all__ = [
    "QueryLlmFunc",
    "StreamQueryBundle",
    "sources_from_llm_result",
    "stream_bundle_from_llm_result",
]