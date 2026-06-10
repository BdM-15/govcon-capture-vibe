"""Environment defaults required by LightRAG cross-provider role validation."""

from __future__ import annotations

import os


def apply_cross_provider_role_env_defaults(environ: dict[str, str] | None = None) -> None:
    """Ensure per-role host/api-key env vars exist when a role binding differs from base LLM.

    LightRAG's ``api/config.py`` exits at import when e.g. ``KEYWORD_LLM_BINDING=ollama``
    while ``LLM_BINDING=openai`` without ``KEYWORD_LLM_BINDING_API_KEY``.
    """
    env = os.environ if environ is None else environ

    if env.get("KEYWORD_LLM_BINDING", "").strip().lower() == "ollama":
        env.setdefault("KEYWORD_LLM_BINDING_HOST", env.get("OLLAMA_HOST", "http://localhost:11434"))
        env.setdefault("KEYWORD_LLM_BINDING_API_KEY", "ollama")