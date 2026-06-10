import os

from src.server.lightrag_env import apply_cross_provider_role_env_defaults


def test_apply_cross_provider_role_env_defaults_for_keyword_ollama(monkeypatch) -> None:
    env = {
        "KEYWORD_LLM_BINDING": "ollama",
        "OLLAMA_HOST": "http://127.0.0.1:11434",
    }
    apply_cross_provider_role_env_defaults(env)
    assert env["KEYWORD_LLM_BINDING_HOST"] == "http://127.0.0.1:11434"
    assert env["KEYWORD_LLM_BINDING_API_KEY"] == "ollama"


def test_apply_cross_provider_role_env_defaults_noop_for_openai_keyword(monkeypatch) -> None:
    monkeypatch.delenv("KEYWORD_LLM_BINDING_API_KEY", raising=False)
    env = {"KEYWORD_LLM_BINDING": "openai"}
    apply_cross_provider_role_env_defaults(env)
    assert "KEYWORD_LLM_BINDING_API_KEY" not in env