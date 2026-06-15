"""Compiler run-mode helpers for deterministic merge vs optional brief LLM."""

from __future__ import annotations

import os

_TRUTHY_ENV = frozenset({"1", "true", "yes", "on"})


def compiler_brief_llm_enabled() -> bool:
    """Opt-in LLM voice polish on brief.md after deterministic merge."""
    return str(os.environ.get("COMPILER_BRIEF_LLM", "") or "").strip().lower() in _TRUTHY_ENV