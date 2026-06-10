"""File-backed chat persistence for the Project Theseus UI."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


class ChatStore:
    """Persist UI chats as one JSON file per chat in the active workspace."""

    def __init__(
        self,
        *,
        workspace_dir: Callable[[], Path],
        now: Callable[[], str],
        history_pairs: Callable[[], int],
    ) -> None:
        self._workspace_dir = workspace_dir
        self._now = now
        self._history_pairs = history_pairs

    def chats_dir(self) -> Path:
        folder = self._workspace_dir() / "chats"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def path(self, chat_id: str) -> Path:
        if not _SAFE_ID.match(chat_id):
            raise HTTPException(status_code=400, detail="Invalid chat id")
        return self.chats_dir() / f"{chat_id}.json"

    def read(self, chat_id: str) -> dict[str, Any]:
        path = self.path(chat_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Chat not found")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="Chat file corrupt") from exc

    def write(self, chat: dict[str, Any]) -> None:
        path = self.path(chat["id"])
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(chat, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def summary(chat: dict[str, Any]) -> dict[str, Any]:
        item = {
            "id": chat["id"],
            "title": chat.get("title", "Untitled"),
            "mode": chat.get("mode", "mix"),
            "rfp_context": chat.get("rfp_context"),
            "message_count": len(chat.get("messages", [])),
            "created_at": chat.get("created_at"),
            "updated_at": chat.get("updated_at"),
        }
        if chat.get("handoff_from"):
            item["handoff_from"] = chat["handoff_from"]
        return item

    def list_summaries(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in self.chats_dir().glob("*.json"):
            try:
                items.append(
                    self.summary(json.loads(path.read_text(encoding="utf-8")))
                )
            except Exception:
                continue
        items.sort(key=lambda chat: chat.get("updated_at") or "", reverse=True)
        return items

    def create(
        self,
        *,
        title: str,
        mode: str,
        rfp_context: str | None,
        handoff_from: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        chat_id = uuid.uuid4().hex[:16]
        now = self._now()
        chat = {
            "id": chat_id,
            "title": title.strip() or "New chat",
            "mode": mode,
            "rfp_context": rfp_context,
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
        if handoff_from:
            chat["handoff_from"] = handoff_from
        self.write(chat)
        return chat

    def update(
        self,
        chat_id: str,
        *,
        title: str | None = None,
        mode: str | None = None,
        rfp_context: str | None = None,
    ) -> dict[str, Any]:
        chat = self.read(chat_id)
        if title is not None:
            chat["title"] = title.strip() or chat["title"]
        if mode is not None:
            chat["mode"] = mode
        if rfp_context is not None:
            chat["rfp_context"] = rfp_context or None
        chat["updated_at"] = self._now()
        self.write(chat)
        return chat

    def delete(self, chat_id: str) -> None:
        path = self.path(chat_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Chat not found")
        path.unlink()

    def build_history(
        self,
        chat: dict[str, Any],
        *,
        exclude_last: bool = False,
    ) -> list[dict[str, str]]:
        """Build LightRAG conversation_history from persisted messages."""
        messages = chat.get("messages", [])
        if exclude_last and messages:
            messages = messages[:-1]
        cleaned = [
            {
                "role": message.get("role", "user"),
                "content": str(message.get("content", "")),
            }
            for message in messages
            if message.get("role") in ("user", "assistant") and message.get("content")
        ]
        cap = self._history_pairs()
        if cap > 0:
            return cleaned[-(cap * 2) :]
        return cleaned

    @staticmethod
    def maybe_autotitle(chat: dict[str, Any], content: str, max_len: int = 60) -> None:
        if chat.get("title") not in (None, "", "New chat"):
            return
        chat["title"] = (
            content[:max_len] + "\u2026" if len(content) > max_len else content
        )
