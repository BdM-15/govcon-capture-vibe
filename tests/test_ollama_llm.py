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


def test_warmup_ollama_sync_marks_ready_when_generate_succeeds(monkeypatch) -> None:
    settings = SimpleNamespace(
        ollama_model="qwen3.5:9b",
        ollama_host="http://localhost:11434",
        keyword_llm_binding="ollama",
        keyword_llm_name="qwen3.5:9b",
        keyword_uses_ollama=True,
    )
    monkeypatch.setattr(
        ollama_llm,
        "list_available_models",
        lambda host, timeout=2.0: ["qwen3.5:9b"],
    )
    monkeypatch.setattr(ollama_llm, "_generate_sync", lambda **kwargs: "ready")

    status = ollama_llm.warmup_ollama_sync(settings)

    assert status["ok"] is True
    assert status["state"] == "ready"
    assert status["model"] == "qwen3.5:9b"


def test_format_ollama_banner_line_shows_ready_state() -> None:
    class _Colors:
        CYAN = "<c>"
        DIM = "<d>"
        BOLD = "<b>"
        GREEN = "<g>"
        RESET = "</>"

    settings = SimpleNamespace(ollama_model="qwen3.5:9b", ollama_host="http://localhost:11434")
    line = ollama_llm.format_ollama_banner_line(
        {"ok": True, "state": "ready", "model": "qwen3.5:9b"},
        settings,
        _Colors,
    )
    assert "qwen3.5:9b" in line
    assert "READY" in line