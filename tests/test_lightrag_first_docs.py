from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parent.parent


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_readme_describes_native_lightrag_ingestion_and_operator_reprocessing() -> None:
    source = _read("README.md")

    for phrase in (
        "LightRAG-first",
        "native LightRAG ingestion",
        "LIGHTRAG_PARSER",
        "MINERU_API_MODE",
        "reprocess the workspace",
    ):
        assert phrase in source

    assert "MINERU PARSING (via RAG-Anything)" not in source
    assert "RAGAnything Multimodal" not in source


def test_env_example_presents_legacy_raganything_settings_as_compatibility_only() -> None:
    source = _read(".env.example")

    assert "Native LightRAG parser routing" in source
    assert "Temporary compatibility settings" in source
    assert "LEGACY RAG-ANYTHING CONTEXT COMPATIBILITY" not in source
    assert "LEGACY MINERU ALIASES" not in source


def test_logs_readme_uses_lightrag_first_startup_and_processing_language() -> None:
    source = _read("logs/README.md")

    assert "native LightRAG parser pipeline" in source
    assert "LightRAG-first Capture Workbench Starting" in source
    assert "Document upload and parsing (RAG-Anything, MinerU)" not in source
    assert "RAG-Anything Server Starting" not in source