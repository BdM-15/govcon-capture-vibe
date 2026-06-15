"""Tests for compiler mode env flags."""

from __future__ import annotations

import pytest

from src.skills.compiler_mode import compiler_brief_llm_enabled


def test_compiler_brief_llm_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPILER_BRIEF_LLM", raising=False)
    assert compiler_brief_llm_enabled() is False


def test_compiler_brief_llm_enabled_with_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPILER_BRIEF_LLM", "1")
    assert compiler_brief_llm_enabled() is True