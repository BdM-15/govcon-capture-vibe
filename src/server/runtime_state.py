"""Active native LightRAG runtime registry."""

from __future__ import annotations

from typing import Any


_active_rag_instance: Any | None = None
_ollama_status: dict[str, Any] | None = None
_langgraph_studio_status: dict[str, Any] | None = None
_langsmith_status: dict[str, Any] | None = None
_server_code_fingerprint: str | None = None


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


def set_langgraph_studio_status(status: dict[str, Any] | None) -> None:
    global _langgraph_studio_status
    _langgraph_studio_status = dict(status) if status else None


def get_langgraph_studio_status() -> dict[str, Any] | None:
    if _langgraph_studio_status is None:
        return None
    return dict(_langgraph_studio_status)


def clear_langgraph_studio_status() -> None:
    set_langgraph_studio_status(None)


def set_langsmith_status(status: dict[str, Any] | None) -> None:
    global _langsmith_status
    _langsmith_status = dict(status) if status else None


def get_langsmith_status() -> dict[str, Any] | None:
    if _langsmith_status is None:
        return None
    return dict(_langsmith_status)


def clear_langsmith_status() -> None:
    set_langsmith_status(None)


def set_server_code_fingerprint(fingerprint: str | None) -> None:
    global _server_code_fingerprint
    value = str(fingerprint or "").strip()
    _server_code_fingerprint = value or None


def get_server_code_fingerprint() -> str | None:
    return _server_code_fingerprint