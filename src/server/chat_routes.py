"""Chat feature routes and per-workspace query settings for Project Theseus UI."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.core.env import env_int
from src.server.chat_store import ChatStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reasoning-block filter (inlined from reasoning_filter)
# ---------------------------------------------------------------------------

_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK = re.compile(r"<think>.*$", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """Remove <think>...</think> blocks from complete string."""
    if not text or "<think>" not in text.lower():
        return text
    cleaned = _THINK_BLOCK.sub("", text)
    cleaned = _UNCLOSED_THINK.sub("", cleaned)
    return cleaned.lstrip()


class ThinkStripper:
    """Stateful streaming filter that strips <think>...</think> blocks."""

    OPEN = "<think>"
    CLOSE = "</think>"
    _HOLD = len(CLOSE)

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    def feed(self, chunk: str) -> str:
        """Consume one chunk, return safe-to-emit text outside <think>."""
        if not chunk:
            return ""
        self._buf += chunk
        out: list[str] = []
        while True:
            if self._in_think:
                idx = self._buf.find(self.CLOSE)
                if idx == -1:
                    if len(self._buf) > self._HOLD:
                        self._buf = self._buf[-self._HOLD:]
                    return "".join(out)
                self._buf = self._buf[idx + len(self.CLOSE):].lstrip()
                self._in_think = False
                continue

            idx = self._buf.find(self.OPEN)
            if idx == -1:
                if len(self._buf) > self._HOLD:
                    out.append(self._buf[:-self._HOLD])
                    self._buf = self._buf[-self._HOLD:]
                return "".join(out)
            if idx > 0:
                out.append(self._buf[:idx])
            self._buf = self._buf[idx + len(self.OPEN):]
            self._in_think = True

    def flush(self) -> str:
        """Drain remaining buffered text at end of stream."""
        if self._in_think:
            self._buf = ""
            return ""
        out = self._buf
        self._buf = ""
        return out

VALID_QUERY_MODES = {"local", "global", "hybrid", "naive", "mix", "bypass"}

# QueryParam fields forwarded to the bridge. `min_rerank_score` is applied
# directly to the LightRAG instance, and `mode` / `stream` are per-chat.
# `response_type` is intentionally omitted because upstream LightRAG WebUI
# dropped the picker and uses QueryParam's default.
QUERY_PARAM_FIELDS = (
    "top_k",
    "chunk_top_k",
    "max_entity_tokens",
    "max_relation_tokens",
    "max_total_tokens",
    "enable_rerank",
    "only_need_context",
    "only_need_prompt",
    "user_prompt",
)

_SOURCE_PREVIEW_CHARS = 800

QueryFunc = Callable[
    [str, str, list[dict], bool, dict],
    Awaitable[str | AsyncIterator[str]],
]
QueryDataFunc = Callable[
    [str, str, list[dict], dict],
    Awaitable[dict],
]


class QuerySettingsUpdate(BaseModel):
    """Per-workspace LightRAG query parameter overrides."""

    mode: str | None = Field(default=None, max_length=20)
    top_k: int | None = Field(default=None, ge=1, le=500)
    chunk_top_k: int | None = Field(default=None, ge=1, le=500)
    max_entity_tokens: int | None = Field(default=None, ge=100, le=200000)
    max_relation_tokens: int | None = Field(default=None, ge=100, le=200000)
    max_total_tokens: int | None = Field(default=None, ge=100, le=500000)
    enable_rerank: bool | None = None
    min_rerank_score: float | None = Field(default=None, ge=0.0, le=1.0)
    only_need_context: bool | None = None
    only_need_prompt: bool | None = None
    stream: bool | None = None
    user_prompt: str | None = Field(default=None, max_length=20000)


class QuerySettingsStore:
    """JSON-backed query settings for active workspace."""

    def __init__(
        self,
        *,
        workspace_dir: Callable[[], Path],
        settings_provider: Callable[[], Any],
    ) -> None:
        self._workspace_dir = workspace_dir
        self._settings_provider = settings_provider

    def defaults(self) -> dict[str, Any]:
        """Build defaults from env-driven server settings."""
        settings = self._settings_provider()
        return {
            "mode": "mix",
            "top_k": env_int("TOP_K", 40, 1, 500),
            "chunk_top_k": env_int("CHUNK_TOP_K", 20, 1, 500),
            "max_entity_tokens": env_int("MAX_ENTITY_TOKENS", 6000, 100, 200000),
            "max_relation_tokens": env_int("MAX_RELATION_TOKENS", 8000, 100, 200000),
            "max_total_tokens": env_int("MAX_TOTAL_TOKENS", 60000, 100, 500000),
            "enable_rerank": bool(settings.enable_rerank),
            "min_rerank_score": float(settings.min_rerank_score),
            "only_need_context": False,
            "only_need_prompt": False,
            "stream": True,
            "user_prompt": "",
        }

    def path(self) -> Path:
        return self._workspace_dir() / "ui_query_settings.json"

    def read(self) -> dict[str, Any]:
        """Return active query settings merged over defaults."""
        path = self.path()
        merged = self.defaults()
        if not path.exists():
            return merged
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key in list(merged.keys()):
                    if key in loaded:
                        merged[key] = loaded[key]
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed reading %s, using defaults: %s", path, exc)
        return merged

    def write(self, data: dict[str, Any]) -> None:
        """Persist query settings atomically."""
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def reset(self) -> dict[str, Any]:
        """Remove overrides and return fresh defaults."""
        path = self.path()
        if path.exists():
            path.unlink()
        return self.defaults()

    def build_overrides(self) -> dict[str, Any]:
        """Build dict passed to bridge QueryParam layer."""
        settings = self.read()
        overrides: dict[str, Any] = {
            key: settings[key] for key in QUERY_PARAM_FIELDS if key in settings
        }
        overrides["min_rerank_score"] = settings.get("min_rerank_score", 0.0)
        return overrides


def register_query_settings_routes(
    app: FastAPI,
    *,
    workspace_name: Callable[[], str],
    store: QuerySettingsStore,
) -> None:
    """Register query settings routes for Theseus UI."""

    @app.get("/api/ui/settings/query", tags=["theseus-ui"])
    async def get_query_settings() -> JSONResponse:
        """Return active per-workspace query settings and defaults."""
        return JSONResponse(
            {
                "workspace": workspace_name(),
                "settings": store.read(),
                "defaults": store.defaults(),
            }
        )

    @app.put("/api/ui/settings/query", tags=["theseus-ui"])
    async def update_query_settings(payload: QuerySettingsUpdate) -> JSONResponse:
        """Patch one or more query settings."""
        current = store.read()
        updates = payload.model_dump(exclude_none=True)
        if "mode" in updates and updates["mode"] not in VALID_QUERY_MODES:
            raise HTTPException(400, f"Unsupported mode: {updates['mode']}")
        current.update(updates)
        try:
            store.write(current)
        except OSError as exc:
            raise HTTPException(500, f"Failed writing settings: {exc}") from exc
        return JSONResponse({"settings": current})

    @app.post("/api/ui/settings/query/reset", tags=["theseus-ui"])
    async def reset_query_settings() -> JSONResponse:
        """Restore defaults by removing per-workspace overrides."""
        try:
            settings = store.reset()
        except OSError as exc:
            raise HTTPException(500, f"Failed resetting settings: {exc}") from exc
        return JSONResponse({"settings": settings})

class ChatCreate(BaseModel):
    """Body for POST /api/ui/chats."""

    title: str = Field(default="New chat", max_length=120)
    mode: str = Field(default="mix")
    rfp_context: str | None = Field(default=None, max_length=200)


class ChatUpdate(BaseModel):
    """Body for PATCH /api/ui/chats/{chat_id}."""

    title: str | None = Field(default=None, max_length=120)
    mode: str | None = Field(default=None)
    rfp_context: str | None = Field(default=None, max_length=200)


class ChatMessageCreate(BaseModel):
    """Body for chat message endpoints."""

    content: str = Field(..., min_length=1, max_length=20000)


def trim_sources(data: dict) -> dict:
    """Project LightRAG aquery_data['data'] into compact UI payload."""
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


def register_chat_routes(
    app: FastAPI,
    *,
    chat_store: ChatStore,
    query_settings: Any,
    query_func: QueryFunc,
    data_func: QueryDataFunc | None,
    now: Callable[[], str],
) -> None:
    """Register persistent chat CRUD plus chat message routes."""

    @app.get("/api/ui/chats", tags=["theseus-ui"])
    async def list_chats() -> JSONResponse:
        """List all saved chats for active workspace, newest first."""
        return JSONResponse({"chats": chat_store.list_summaries()})

    @app.post("/api/ui/chats", tags=["theseus-ui"])
    async def create_chat(payload: ChatCreate) -> JSONResponse:
        """Create new persistent chat session."""
        chat = chat_store.create(
            title=payload.title,
            mode=payload.mode,
            rfp_context=payload.rfp_context,
        )
        return JSONResponse(chat_store.summary(chat), status_code=201)

    @app.get("/api/ui/chats/{chat_id}", tags=["theseus-ui"])
    async def get_chat(chat_id: str) -> JSONResponse:
        """Return full chat including all messages."""
        return JSONResponse(chat_store.read(chat_id))

    @app.patch("/api/ui/chats/{chat_id}", tags=["theseus-ui"])
    async def update_chat(chat_id: str, payload: ChatUpdate) -> JSONResponse:
        """Rename chat or update mode / RFP context."""
        chat = chat_store.update(
            chat_id,
            title=payload.title,
            mode=payload.mode,
            rfp_context=payload.rfp_context,
        )
        return JSONResponse(chat_store.summary(chat))

    @app.delete("/api/ui/chats/{chat_id}", tags=["theseus-ui"])
    async def delete_chat(chat_id: str) -> JSONResponse:
        """Permanently delete chat."""
        chat_store.delete(chat_id)
        return JSONResponse({"status": "deleted", "id": chat_id})

    @app.post("/api/ui/chats/{chat_id}/messages", tags=["theseus-ui"])
    async def post_message(chat_id: str, payload: ChatMessageCreate) -> JSONResponse:
        """Append user message, invoke RAG query, persist assistant reply."""
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
        """Stream assistant reply token-by-token via SSE."""
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


__all__ = [
    "ChatCreate",
    "ChatMessageCreate",
    "ChatUpdate",
    "ChatStore",
    "QuerySettingsStore",
    "ThinkStripper",
    "register_chat_routes",
    "register_query_settings_routes",
    "strip_think",
    "trim_sources",
]