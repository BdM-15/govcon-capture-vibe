import os

from theseus_bootstrap_env import apply_theseus_env_defaults


def test_apply_theseus_env_defaults_for_local_keyword() -> None:
    env = {
        "THESEUS_KEYWORD_USE_OLLAMA": "true",
        "OLLAMA_HOST": "http://127.0.0.1:11434",
    }
    apply_theseus_env_defaults(env)
    assert env["KEYWORD_LLM_BINDING"] == "openai"
    assert env["KEYWORD_LLM_BINDING_HOST"] == "http://127.0.0.1:11434/v1"
    assert env["KEYWORD_LLM_BINDING_API_KEY"] == "ollama"


def test_apply_theseus_env_defaults_migrates_legacy_ollama_binding() -> None:
    env = {
        "KEYWORD_LLM_BINDING": "ollama",
        "OLLAMA_HOST": "http://localhost:11434",
    }
    apply_theseus_env_defaults(env)
    assert env["THESEUS_KEYWORD_USE_OLLAMA"] == "true"
    assert env["KEYWORD_LLM_BINDING"] == "openai"
    assert env["KEYWORD_LLM_BINDING_HOST"] == "http://localhost:11434/v1"


def test_apply_theseus_env_defaults_noop_when_disabled() -> None:
    env = {"THESEUS_KEYWORD_USE_OLLAMA": "false"}
    apply_theseus_env_defaults(env)
    assert "KEYWORD_LLM_BINDING_HOST" not in env