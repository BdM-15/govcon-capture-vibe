"""Chat message and streaming routes for the Project Theseus UI."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.server.reasoning_filter import ThinkStripper, strip_think

logger = logging.getLogger(__name__)

QueryFunc = Callable[
    [str, str, list[dict], bool, dict],
    Awaitable[str | AsyncIterator[str]],
]
QueryDataFunc = Callable[
    [str, str, list[dict], dict],
    Awaitable[dict],
]

_SOURCE_PREVIEW_CHARS = 800


class ChatMessageCreate(BaseModel):
    """Body for chat message endpoints."""

    content: str = Field(..., min_length=1, max_length=20000)


def trim_sources(data: dict) -> dict:
    """Project LightRAG aquery_data['data'] into a compact UI payload."""
    chunks_in = data.get("chunks") or []
    refs_in = data.get("references") or []
    ents_in = data.get("entities") or []
    rels_in = data.get("relationships") or []

    chunks_out = []
    for chunk in chunks_in:
        if not isinstance(chunk, dict):
            continue
        content = str(chunk.get("content") or "")
        truncated = len(content) > _SOURCE_PREVIEW_CHARS
        preview = content[:_SOURCE_PREVIEW_CHARS] + ("…" if truncated else "")
        chunks_out.append(
            {
                "reference_id": str(chunk.get("reference_id") or ""),
                "chunk_id": str(chunk.get("chunk_id") or ""),
                "file_path": str(chunk.get("file_path") or ""),
                "preview": preview,
                "char_count": len(content),
                "truncated": truncated,
            }
        )

    refs_out = [
        {
            "reference_id": str(reference.get("reference_id") or ""),
            "file_path": str(reference.get("file_path") or ""),
        }
        for reference in refs_in
        if isinstance(reference, dict)
    ]

    return {
        "chunks": chunks_out,
        "references": refs_out,
        "counts": {
            "chunks": len(chunks_out),
            "entities": len(ents_in),
            "relationships": len(rels_in),
            "references": len(refs_out),
        },
    }


def register_chat_message_routes(
    app: FastAPI,
    *,
    chat_store: Any,
    query_settings: Any,
    query_func: QueryFunc,
    data_func: QueryDataFunc | None,
    now: Callable[[], str],
) -> None:
    """Register sync and streaming chat message routes."""

    @app.post("/api/ui/chats/{chat_id}/messages", tags=["theseus-ui"])
    async def post_message(chat_id: str, payload: ChatMessageCreate) -> JSONResponse:
        """Append a user message, invoke RAG query, persist the assistant reply."""
        chat = chat_store.read(chat_id)
        user_msg = {
            "role": "user",
            "content": payload.content,
            "ts": now(),
        }
        chat["messages"].append(user_msg)

        history = chat_store.build_history(chat, exclude_last=True)
        overrides = query_settings.build_overrides()
        try:
            answer = await query_func(
                payload.content,
                chat.get("mode", "mix"),
                history,
                False,
                overrides,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Query failed for chat %s: %s", chat_id, exc)
            answer = f"⚠️ Query failed: {exc}"

        assistant_msg = {
            "role": "assistant",
            "content": strip_think(str(answer)),
            "ts": now(),
            "mode": chat.get("mode", "mix"),
        }
        chat["messages"].append(assistant_msg)
        chat["updated_at"] = now()

        if chat.get("title") in (None, "", "New chat") and len(chat["messages"]) <= 2:
            chat_store.maybe_autotitle(chat, payload.content)

        chat_store.write(chat)
        return JSONResponse(
            {
                "user": user_msg,
                "assistant": assistant_msg,
                "chat": chat_store.summary(chat),
            }
        )

    @app.post("/api/ui/chats/{chat_id}/messages/stream", tags=["theseus-ui"])
    async def post_message_stream(
        chat_id: str,
        payload: ChatMessageCreate,
    ) -> StreamingResponse:
        """Stream the assistant reply token-by-token via SSE."""
        chat = chat_store.read(chat_id)
        user_msg = {
            "role": "user",
            "content": payload.content,
            "ts": now(),
        }
        chat["messages"].append(user_msg)
        if chat.get("title") in (None, "", "New chat") and len(chat["messages"]) <= 1:
            chat_store.maybe_autotitle(chat, payload.content)
        chat_store.write(chat)

        history = chat_store.build_history(chat, exclude_last=True)
        mode = chat.get("mode", "mix")
        overrides = query_settings.build_overrides()

        async def event_stream() -> AsyncIterator[str]:
            yield "event: open\ndata: {}\n\n"
            yield (
                "event: status\ndata: "
                + json.dumps({"phase": "retrieving", "label": "Retrieving context…"})
                + "\n\n"
            )
            collected: list[str] = []
            stripper = ThinkStripper()
            start = time.perf_counter()
            first_token: float | None = None
            token_count = 0
            error_message: str | None = None
            sources_payload: dict | None = None
            try:
                if data_func is not None and mode != "bypass":
                    try:
                        data_result = await data_func(
                            payload.content,
                            mode,
                            history,
                            overrides,
                        )
                        if isinstance(data_result, dict) and data_result.get("status") == "success":
                            sources_payload = trim_sources(data_result.get("data", {}))
                            yield (
                                "event: sources\ndata: "
                                + json.dumps(sources_payload)
                                + "\n\n"
                            )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Sources pre-flight failed for chat %s: %s",
                            chat_id,
                            exc,
                        )
                result = await query_func(payload.content, mode, history, True, overrides)
                retrieve_ms = int((time.perf_counter() - start) * 1000)
                yield (
                    "event: status\ndata: "
                    + json.dumps(
                        {
                            "phase": "generating",
                            "label": "Generating response…",
                            "retrieve_ms": retrieve_ms,
                        }
                    )
                    + "\n\n"
                )
                if hasattr(result, "__aiter__"):
                    async for chunk in result:
                        if not chunk:
                            continue
                        text = stripper.feed(str(chunk))
                        if not text:
                            continue
                        if first_token is None:
                            first_token = time.perf_counter()
                        collected.append(text)
                        token_count += 1
                        yield f"event: token\ndata: {json.dumps({'text': text})}\n\n"
                    tail = stripper.flush()
                    if tail:
                        if first_token is None:
                            first_token = time.perf_counter()
                        collected.append(tail)
                        token_count += 1
                        yield f"event: token\ndata: {json.dumps({'text': tail})}\n\n"
                else:
                    text = strip_think(str(result))
                    collected.append(text)
                    token_count = 1
                    first_token = time.perf_counter()
                    yield f"event: token\ndata: {json.dumps({'text': text})}\n\n"
            except Exception as exc:  # noqa: BLE001
                logger.exception("Streaming query failed for chat %s", chat_id)
                error_message = str(exc)
                yield f"event: error\ndata: {json.dumps({'message': error_message})}\n\n"
                collected.append(f"⚠️ Query failed: {exc}")

            end = time.perf_counter()
            total_ms = int((end - start) * 1000)
            ttft_ms = int((first_token - start) * 1000) if first_token else None
            generate_ms = int((end - first_token) * 1000) if first_token else None

            full_text = "".join(collected)
            timing = {
                "total_ms": total_ms,
                "ttft_ms": ttft_ms,
                "generate_ms": generate_ms,
                "chunk_count": token_count,
                "char_count": len(full_text),
            }
            assistant_msg = {
                "role": "assistant",
                "content": full_text,
                "ts": now(),
                "mode": mode,
                "timing": timing,
            }
            if sources_payload is not None:
                assistant_msg["sources"] = sources_payload
            try:
                latest = chat_store.read(chat_id)
            except HTTPException:
                latest = chat
            latest["messages"].append(assistant_msg)
            latest["updated_at"] = now()
            chat_store.write(latest)

            logger.info(
                "[chat] mode=%s ttft=%sms total=%sms chunks=%s chars=%s%s",
                mode,
                ttft_ms if ttft_ms is not None else "-",
                total_ms,
                token_count,
                len(full_text),
                f" error={error_message!r}" if error_message else "",
            )

            yield (
                "event: done\ndata: "
                + json.dumps(
                    {
                        "assistant": assistant_msg,
                        "chat": chat_store.summary(latest),
                        "timing": timing,
                    }
                )
                + "\n\n"
            )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )