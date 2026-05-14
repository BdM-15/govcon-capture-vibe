"""Tracer-bullet test for src/server/vault_capture.py::capture.

Exercises the full classify -> polish -> wikilink-suggest -> persist round-trip
through the public ``capture`` interface.  Mocks the LLM via an injected
async callable that mirrors the contract of vault_llm.polish_note's llm_func
(``(prompt, system_prompt=...) -> str`` returning TYPE/TITLE/BODY).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.server.vault_capture import CapturedNote, capture
from src.server.vault_store import VaultStore


def test_capture_returns_classified_polished_note_persisted_to_vault(
    tmp_path: Path,
):
    # arrange ----------------------------------------------------------------
    raw = "competitor X just won an idiq for cleared workforce work, big deal"

    async def fake_llm(prompt, system_prompt=""):
        # Simulate vault-curation LLM: classify + polish in one TYPE/TITLE/BODY response
        return (
            "TYPE: insight\n"
            "TITLE: Competitor X wins cleared workforce IDIQ\n"
            "BODY: Competitor X recently won an [[Cleared Workforce]] IDIQ. "
            "This is a significant competitive signal worth tracking."
        )

    vault_store = VaultStore(tmp_path, now=lambda: "2026-05-14T12:00:00")
    vault_index = {
        "Cleared Workforce": "cleared-workforce",
        "Capture Plan Development": "capture-plan-development",
    }

    # act --------------------------------------------------------------------
    async def _run():
        return await capture(
            raw_body=raw,
            llm_func=fake_llm,
            vault_store=vault_store,
            vault_index=vault_index,
            auto_polish=True,
        )

    captured = asyncio.run(_run())

    # assert -----------------------------------------------------------------
    assert isinstance(captured, CapturedNote)
    assert captured.note_type == "insight"
    assert captured.title == "Competitor X wins cleared workforce IDIQ"
    assert captured.auto_polished is True
    assert captured.raw_body == raw
    assert "Competitor X" in captured.polished_body
    assert captured.polished_body != raw  # actual rewrite happened
    assert "[[Cleared Workforce]]" in captured.wikilink_suggestions

    # persisted to disk
    assert captured.path.exists()
    assert captured.path.parent == tmp_path

    # readable back through VaultStore public interface
    persisted = vault_store.read(captured.note_id)
    assert persisted["type"] == "insight"
    assert persisted["title"] == captured.title
    assert "Competitor X" in persisted["body"]


def test_capture_rejects_empty_body(tmp_path):
    """Whitespace-only / empty body must raise ValueError before any LLM call."""
    vault_store = VaultStore(tmp_path, now=lambda: "2026-05-14T12:00:00")
    called = []

    async def boom_llm(prompt, system_prompt=""):
        called.append(prompt)
        return "TYPE: raw\nTITLE: x\nBODY: x"

    async def _run(body):
        await capture(
            raw_body=body,
            llm_func=boom_llm,
            vault_store=vault_store,
            vault_index={},
            auto_polish=True,
        )

    for empty in ("", "   ", "\n\n\t"):
        with pytest.raises(ValueError, match="empty"):
            asyncio.run(_run(empty))

    assert called == [], "LLM must not be called for empty body"
    assert list(tmp_path.glob("*.md")) == [], "no file should be persisted"


def test_capture_falls_back_to_raw_when_llm_raises(tmp_path):
    """LLM failure during auto_polish must NOT crash; persist as raw note."""
    vault_store = VaultStore(tmp_path, now=lambda: "2026-05-14T12:00:00")

    async def bad_llm(prompt, system_prompt=""):
        raise RuntimeError("ollama is down")

    raw = "lost the recompete on AFCAP because BAFO too high"

    async def _run():
        return await capture(
            raw_body=raw,
            llm_func=bad_llm,
            vault_store=vault_store,
            vault_index={},
            auto_polish=True,
        )

    captured = asyncio.run(_run())

    assert captured.note_type == "raw"
    assert captured.auto_polished is False  # degraded
    assert captured.polished_body == raw
    assert captured.raw_body == raw
    assert captured.path.exists()
    assert "lost the recompete" in captured.title.lower()


def test_capture_skips_llm_when_auto_polish_false(tmp_path):
    """auto_polish=False persists raw note without invoking the LLM."""
    vault_store = VaultStore(tmp_path, now=lambda: "2026-05-14T12:00:00")
    called = []

    async def llm(prompt, system_prompt=""):
        called.append(prompt)
        return "TYPE: insight\nTITLE: x\nBODY: x"

    raw = "quick capture, no polish wanted"

    async def _run():
        return await capture(
            raw_body=raw,
            llm_func=llm,
            vault_store=vault_store,
            vault_index={"Anything": "anything"},
            auto_polish=False,
        )

    captured = asyncio.run(_run())

    assert called == [], "LLM must not be invoked when auto_polish=False"
    assert captured.note_type == "raw"
    assert captured.auto_polished is False
    assert captured.polished_body == raw
    assert captured.wikilink_suggestions == []
    assert captured.path.exists()


def test_capture_status_reflects_polish_outcome(tmp_path):
    """#153: status='polished' on success+auto_polish, 'raw' otherwise."""

    async def good_llm(prompt, system_prompt=""):
        return "TYPE: insight\nTITLE: t\nBODY: b"

    async def bad_llm(prompt, system_prompt=""):
        raise RuntimeError("down")

    def _store(name):
        d = tmp_path / name
        d.mkdir()
        return VaultStore(d, now=lambda: "2026-05-14T12:00:00")

    async def _do(llm, auto, name):
        return await capture(
            raw_body="something to capture",
            llm_func=llm,
            vault_store=_store(name),
            vault_index={},
            auto_polish=auto,
        )

    polished = asyncio.run(_do(good_llm, True, "a"))
    raw_by_choice = asyncio.run(_do(good_llm, False, "b"))
    raw_by_failure = asyncio.run(_do(bad_llm, True, "c"))

    assert polished.status == "polished"
    assert raw_by_choice.status == "raw"
    assert raw_by_failure.status == "raw"

    # persisted on disk
    assert "status: polished" in polished.path.read_text(encoding="utf-8")
    assert "status: raw" in raw_by_choice.path.read_text(encoding="utf-8")
    assert "status: raw" in raw_by_failure.path.read_text(encoding="utf-8")
