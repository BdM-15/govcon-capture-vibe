from types import SimpleNamespace

from src.server import ollama_llm


def test_pick_best_model_prefers_configured_tag() -> None:
    assert ollama_llm.pick_best_model("qwen3.5:9b", ["llama3.1", "qwen3.5:9b"]) == "qwen3.5:9b"


def test_pick_best_model_falls_back_to_instruct_family() -> None:
    chosen = ollama_llm.pick_best_model(
        "missing-model",
        ["nomic-embed-text", "llama3.1:8b-instruct"],
    )
    assert chosen == "llama3.1:8b-instruct"


def test_resolve_ollama_model_uses_settings_default(monkeypatch) -> None:
    monkeypatch.setattr(ollama_llm, "list_available_models", lambda host, timeout=2.0: [])
    settings = SimpleNamespace(ollama_model="qwen3.5:9b", ollama_host="http://localhost:11434")
    assert ollama_llm.resolve_ollama_model(settings) == "qwen3.5:9b"