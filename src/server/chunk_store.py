"""Cached read-only access to workspace kv_store_text_chunks.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, int, dict[str, Any]]] = {}
_lock = Lock()


def get_text_chunk(chunks_path: Path, chunk_id: str) -> dict[str, Any] | None:
    """Return one chunk record; reload store when mtime or size changes."""
    if not chunks_path.exists():
        return None

    try:
        stat = chunks_path.stat()
        mtime = stat.st_mtime
        size = stat.st_size
    except OSError as exc:
        logger.warning("Failed stat %s: %s", chunks_path, exc)
        return None

    key = str(chunks_path.resolve())
    with _lock:
        cached = _cache.get(key)
        if cached is None or cached[0] != mtime or cached[1] != size:
            try:
                store = json.loads(chunks_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Failed reading text-chunk store %s: %s", chunks_path, exc)
                return None
            if not isinstance(store, dict):
                return None
            _cache[key] = (mtime, size, store)
            cached = _cache[key]

    chunk = cached[2].get(chunk_id)
    return chunk if isinstance(chunk, dict) else None


def clear_chunk_store_cache() -> None:
    """Drop cached stores (tests only)."""
    with _lock:
        _cache.clear()


__all__ = ["clear_chunk_store_cache", "get_text_chunk"]