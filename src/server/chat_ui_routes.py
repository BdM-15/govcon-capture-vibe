"""Persistent chat routes for the Project Theseus UI."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.server.chat_store import ChatStore
from src.server.chat_message_ui_routes import register_chat_message_routes, trim_sources

logger = logging.getLogger(__name__)


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


def register_chat_ui_routes(
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
        """List all saved chats for the active workspace, newest first."""
        return JSONResponse({"chats": chat_store.list_summaries()})

    @app.post("/api/ui/chats", tags=["theseus-ui"])
    async def create_chat(payload: ChatCreate) -> JSONResponse:
        """Create a new persistent chat session."""
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
        """Rename a chat or update its mode / RFP context."""
        chat = chat_store.update(
            chat_id,
            title=payload.title,
            mode=payload.mode,
            rfp_context=payload.rfp_context,
        )
        return JSONResponse(chat_store.summary(chat))

    @app.delete("/api/ui/chats/{chat_id}", tags=["theseus-ui"])
    async def delete_chat(chat_id: str) -> JSONResponse:
        """Permanently delete a chat."""
        chat_store.delete(chat_id)
        return JSONResponse({"status": "deleted", "id": chat_id})

    register_chat_message_routes(
        app,
        chat_store=chat_store,
        query_settings=query_settings,
        query_func=query_func,
        data_func=data_func,
        now=now,
    )
