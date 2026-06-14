"""Tests for unified Ollama admin LLM status and readiness preflight."""

from __future__ import annotations

from unittest.mock import patch

from src.skills.local_llm_admin import admin_llm_status, admin_model_configured
from src.skills.readiness_solo_invoke import (
    preflight_readiness_solo,
    readiness_step_requires_admin_llm,
)


def test_readiness_step_requires_admin_llm_for_eval_and_compile() -> None:
    assert readiness_step_requires_admin_llm("eval") is True
    assert readiness_step_requires_admin_llm("compile") is True
    assert readiness_step_requires_admin_llm("workload") is False


def test_preflight_workload_ok_when_ollama_down() -> None:
    with patch(
        "src.skills.readiness_solo_invoke.admin_llm_status",
        return_value={"ready": False, "state": "unavailable", "error": "down"},
    ):
        assert preflight_readiness_solo("workload") is None


def test_preflight_eval_blocks_when_ollama_down() -> None:
    status = {
        "ready": False,
        "state": "unavailable",
        "host": "http://localhost:11434",
        "model": "qwen3.5:9b",
        "error": "no models reported",
        "fix_hint": "Start Ollama and pull the configured model.",
    }
    with patch("src.skills.readiness_solo_invoke.admin_llm_status", return_value=status):
        err = preflight_readiness_solo("eval")
    assert err is not None
    assert "Ollama" in err
    assert "eval" in err.lower()


def test_admin_llm_status_uses_settings_ollama(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:9b")
    with (
        patch(
            "src.skills.local_llm_admin.get_ollama_status",
            return_value={
                "ok": True,
                "state": "ready",
                "model": "qwen3.5:9b",
                "host": "http://127.0.0.1:11434",
            },
        ),
        patch("src.skills.local_llm_admin.is_ollama_available", return_value=True),
    ):
        status = admin_llm_status()
        assert status["host"] == "http://127.0.0.1:11434"
        assert status["ready"] is True
        assert status["label"] == "Ollama (local admin)"
        assert admin_model_configured() is True