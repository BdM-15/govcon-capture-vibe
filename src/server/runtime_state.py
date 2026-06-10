"""Active native LightRAG runtime registry."""

from __future__ import annotations

from typing import Any


_active_rag_instance: Any | None = None
_ollama_status: dict[str, Any] | None = None


def set_active_rag_instance(rag_instance: Any | None) -> None:
    global _active_rag_instance
    _active_rag_instance = rag_instance


def get_active_rag_instance() -> Any | None:
    return _active_rag_instance


def clear_active_rag_instance() -> None:
    set_active_rag_instance(None)


def set_ollama_status(status: dict[str, Any] | None) -> None:
    global _ollama_status
    _ollama_status = dict(status) if status else None


def get_ollama_status() -> dict[str, Any] | None:
    if _ollama_status is None:
        return None
    return dict(_ollama_status)


def clear_ollama_status() -> None:
    set_ollama_status(None)