"""Operator template contracts for LightRAG 1.5.x knobs."""

from __future__ import annotations

from pathlib import Path


def test_env_example_documents_max_extract_input_tokens() -> None:
    source = Path(".env.example").read_text(encoding="utf-8")
    assert "MAX_EXTRACT_INPUT_TOKENS=24000" in source
    assert "extract" in source.lower() or "gleaning" in source.lower()