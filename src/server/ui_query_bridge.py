"""UI query bridge helpers for the Theseus server."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass
class UIQueryBridges:
    query: Callable[[str, str, list[dict], bool, dict | None], Awaitable[Any]]
    query_data: Callable[[str, str, list[dict], dict | None], Awaitable[Any]]
    llm: Callable[[str], Awaitable[str]]


def make_ui_query_bridges(
    rag_instance: Any,
    *,
    logger: Any,
    query_param_factory: Any | None = None,
) -> UIQueryBridges:
    """Build the UI-facing query/data/LLM bridge callables."""
    if query_param_factory is None:
        from lightrag import QueryParam as query_param_factory

    valid_fields = {f.name for f in query_param_factory.__dataclass_fields__.values()}

    async def _ui_query(
        text: str,
        mode: str,
        history: list[dict],
        stream: bool,
        overrides: dict | None = None,
    ):
        overrides = dict(overrides or {})
        min_score = overrides.pop("min_rerank_score", None)
        if min_score is not None:
            try:
                rag_instance.lightrag.min_rerank_score = float(min_score)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed setting min_rerank_score=%r: %s", min_score, exc)
        param_kwargs = {k: v for k, v in overrides.items() if k in valid_fields}
        return await rag_instance.lightrag.aquery(
            text,
            param=query_param_factory(
                mode=mode,
                stream=stream,
                conversation_history=history or [],
                **param_kwargs,
            ),
        )

    async def _ui_query_data(
        text: str,
        mode: str,
        history: list[dict],
        overrides: dict | None = None,
    ):
        overrides = dict(overrides or {})
        min_score = overrides.pop("min_rerank_score", None)
        if min_score is not None:
            try:
                rag_instance.lightrag.min_rerank_score = float(min_score)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed setting min_rerank_score=%r: %s", min_score, exc)
        param_kwargs = {k: v for k, v in overrides.items() if k in valid_fields}
        param_kwargs.pop("stream", None)
        return await rag_instance.lightrag.aquery_data(
            text,
            param=query_param_factory(
                mode=mode,
                conversation_history=history or [],
                **param_kwargs,
            ),
        )

    async def _ui_llm(prompt: str) -> str:
        llm = getattr(rag_instance.lightrag, "llm_model_func", None)
        if llm is None:
            raise RuntimeError("LightRAG instance has no llm_model_func configured")
        result = await llm(prompt, system_prompt=None, history_messages=[])
        return result if isinstance(result, str) else str(result)

    return UIQueryBridges(query=_ui_query, query_data=_ui_query_data, llm=_ui_llm)