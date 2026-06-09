"""KG explorer entity chunk drill-down routes."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

def _chunk_ids_for_entity(entity_chunks_map: dict[str, Any], name: str) -> list[str]:
    chunk_ids = entity_chunks_map.get(name) or entity_chunks_map.get(name.strip('"')) or []
    if isinstance(chunk_ids, dict):
        return list(chunk_ids.keys())
    if isinstance(chunk_ids, list):
        return [str(chunk_id) for chunk_id in chunk_ids]
    return []


def load_entity_chunks(workspace_dir: Path, name: str, limit: int = 8) -> dict[str, Any]:
    """Return source text chunk previews that mention entity."""
    entity_chunks_path = workspace_dir / "kv_store_entity_chunks.json"
    text_chunks_path = workspace_dir / "kv_store_text_chunks.json"
    if not entity_chunks_path.exists() or not text_chunks_path.exists():
        return {"entity": name, "chunks": []}
    try:
        entity_chunks_map = json.loads(entity_chunks_path.read_text(encoding="utf-8"))
        text_chunks = json.loads(text_chunks_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed reading chunk stores: %s", exc)
        return {"entity": name, "chunks": []}
    if not isinstance(entity_chunks_map, dict) or not isinstance(text_chunks, dict):
        return {"entity": name, "chunks": []}

    chunks: list[dict[str, Any]] = []
    for chunk_id in _chunk_ids_for_entity(entity_chunks_map, name)[:limit]:
        chunk = text_chunks.get(chunk_id) or {}
        if not isinstance(chunk, dict):
            chunk = {}
        content = chunk.get("content") or chunk.get("text") or ""
        chunks.append(
            {
                "chunk_id": chunk_id,
                "file_path": chunk.get("file_path") or chunk.get("full_doc_id"),
                "chunk_order_index": chunk.get("chunk_order_index"),
                "snippet": content[:600] + ("…" if len(content) > 600 else ""),
            }
        )
    return {"entity": name, "chunks": chunks}


def register_entity_chunk_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
) -> None:
    """Register KG explorer entity drill-down endpoints."""

    @app.get("/api/ui/entity/{name}/chunks", tags=["theseus-ui"])
    async def entity_chunks(name: str, limit: int = 8) -> JSONResponse:
        """Return source text chunks that mention entity."""
        return JSONResponse(load_entity_chunks(workspace_dir(), name, limit=limit))

