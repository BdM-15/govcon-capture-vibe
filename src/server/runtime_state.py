"""Active native LightRAG runtime registry."""

from __future__ import annotations

from typing import Any


_active_rag_instance: Any | None = None


def set_active_rag_instance(rag_instance: Any | None) -> None:
    global _active_rag_instance
    _active_rag_instance = rag_instance


def get_active_rag_instance() -> Any | None:
    return _active_rag_instance


def clear_active_rag_instance() -> None:
    set_active_rag_instance(None)