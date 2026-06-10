"""Tests for cached kv_store_text_chunks.json lookups."""

from __future__ import annotations

import json
from pathlib import Path

from src.server.chunk_store import clear_chunk_store_cache, get_text_chunk


def test_get_text_chunk_uses_mtime_cache(tmp_path: Path, monkeypatch) -> None:
    clear_chunk_store_cache()
    chunks_path = tmp_path / "kv_store_text_chunks.json"
    cid = "chunk-abc"
    chunks_path.write_text(
        json.dumps({cid: {"content": "first", "file_path": "a.pdf"}}),
        encoding="utf-8",
    )

    reads: list[str] = []
    original_read_text = Path.read_text

    def _counting_read_text(self: Path, *args, **kwargs) -> str:
        reads.append(str(self))
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _counting_read_text)

    assert get_text_chunk(chunks_path, cid)["content"] == "first"
    assert get_text_chunk(chunks_path, cid)["content"] == "first"
    assert len(reads) == 1

    chunks_path.write_text(
        json.dumps({cid: {"content": "second", "file_path": "a.pdf"}}),
        encoding="utf-8",
    )
    assert get_text_chunk(chunks_path, cid)["content"] == "second"
    assert len(reads) == 2


def test_get_text_chunk_unknown_id_returns_none(tmp_path: Path) -> None:
    clear_chunk_store_cache()
    chunks_path = tmp_path / "kv_store_text_chunks.json"
    chunks_path.write_text("{}", encoding="utf-8")
    assert get_text_chunk(chunks_path, "missing") is None