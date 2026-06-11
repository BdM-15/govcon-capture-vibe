"""Environment bootstrap before LightRAG imports (used by app.py)."""

from __future__ import annotations

import os


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def apply_theseus_env_defaults(environ: dict[str, str] | None = None) -> None:
    """Apply Theseus-specific env defaults required for safe LightRAG startup."""
    env = os.environ if environ is None else environ

    # Legacy migration: KEYWORD_LLM_BINDING=ollama requires the ollama pip package
    # inside LightRAG's API server. Theseus routes keyword calls through OpenAI-compat
    # (/v1) instead, so normalize binding back to openai.
    if env.get("KEYWORD_LLM_BINDING", "").strip().lower() == "ollama":
        env["THESEUS_KEYWORD_USE_OLLAMA"] = "true"
        env["KEYWORD_LLM_BINDING"] = "openai"

    if not _truthy(env.get("THESEUS_KEYWORD_USE_OLLAMA")):
        return

    host = env.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    env.setdefault("KEYWORD_LLM_BINDING", "openai")
    env.setdefault("KEYWORD_LLM_BINDING_HOST", f"{host}/v1")
    env.setdefault("KEYWORD_LLM_BINDING_API_KEY", "ollama")