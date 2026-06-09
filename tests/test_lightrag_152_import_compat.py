"""Import-compat smoke tests for the pinned LightRAG 1.5.2 runtime."""

from __future__ import annotations

import importlib.util

def test_lightrag_152_critical_symbols_import() -> None:
    from lightrag.chunker import chunking_by_token_size
    from lightrag.lightrag import RoleLLMConfig
    from lightrag.parser.routing import resolve_file_parser_directives
    from lightrag.utils_pipeline import build_chunks_dict_from_chunking_result

    assert RoleLLMConfig is not None
    assert callable(resolve_file_parser_directives)
    assert callable(chunking_by_token_size)
    assert callable(build_chunks_dict_from_chunking_result)


def test_lightrag_152_native_pipeline_module_available() -> None:
    from src.server.native_lightrag_runtime import native_pipeline_available

    assert importlib.util.find_spec("lightrag.pipeline") is not None
    assert native_pipeline_available() is True


def test_lightrag_152_parser_routing_resolves_pdf_mineru() -> None:
    from lightrag.parser.routing import resolve_file_parser_directives

    engine, options = resolve_file_parser_directives(
        "sample.pdf",
        parser_rules="pdf:mineru-ite",
    )
    assert "mineru" in engine