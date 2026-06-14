"""Tests for admin LLM acronym helpers."""

from __future__ import annotations

import asyncio
import json

import pytest

from src.skills.local_llm_admin import admin_model_configured, expand_acronyms_in_eval_handoff_json


def test_expand_acronyms_in_eval_handoff_json_uses_admin_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "eval_crosswalk": [
            {
                "evaluation_factor": "Factor 4 Past Performance",
                "readiness_link": "CPARS ratings drive confidence.",
                "proof_expected": "PPQ references per Section M.",
                "source_chunk_ids": ["chunk-abc"],
            }
        ],
        "claim_gaps": [],
    }
    original = json.dumps(payload, indent=2)

    async def _fake_chat(_prompt: str) -> str:
        fixed = {
            "eval_crosswalk": [
                {
                    "evaluation_factor": "Factor 4 Past Performance",
                    "readiness_link": (
                        "Contractor Performance Assessment Reporting System (CPARS) "
                        "ratings drive confidence."
                    ),
                    "proof_expected": (
                        "Past Performance Questionnaire (PPQ) references per Section M."
                    ),
                    "source_chunk_ids": ["chunk-abc"],
                }
            ],
            "claim_gaps": [],
        }
        return json.dumps(fixed)

    monkeypatch.delenv("THESEUS_ADMIN_LLM_MODEL", raising=False)
    monkeypatch.delenv("THESEUS_ADMIN_LLM_HOST", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:9b")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")

    assert admin_model_configured()
    revised = asyncio.run(
        expand_acronyms_in_eval_handoff_json(original, chat_fn=_fake_chat)
    )
    loaded = json.loads(revised)
    readiness = loaded["eval_crosswalk"][0]["readiness_link"]
    assert "Contractor Performance Assessment Reporting System (CPARS)" in readiness