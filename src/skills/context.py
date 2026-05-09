"""Workspace context builders for skill invocation.

This module owns the skill briefing-book interface: given a workspace storage
folder and optional retrieval helper, produce the deterministic evidence payload
that legacy skills receive and tools-mode skills can fetch through kg_* tools.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

_RETRIEVED_ENTITY_DETAIL_LIMIT = 8
_RETRIEVED_CHUNK_DETAIL_LIMIT = 4
_RETRIEVED_SUMMARY_LIMIT = 180
_RETRIEVED_SNIPPET_LIMIT = 260

QueryDataFunc = Callable[
    [str, str, list[dict], dict],
    Awaitable[dict],
]


class SkillWorkspaceEvidenceStore:
    """Own workspace VDB file layout + evidence shaping for skills."""

    _NOISE_BUCKETS = {"concept", "unknown"}

    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = Path(workspace_dir)

    def build_briefing_book(
        self,
        entity_types: Optional[list[str]],
        max_per_type: int,
        max_chunks_per_entity: int = 2,
        max_relationships_per_entity: int = 5,
        relevant_entity_names: Optional[set[str]] = None,
    ) -> dict[str, Any]:
        """Build source-grounded evidence payload for one skill run."""

        records = self._read_records("vdb_entities.json")
        if not records:
            return {"entities": {}, "source_chunks": [], "relationships": []}

        wanted = {entity_type.lower() for entity_type in entity_types} if entity_types else None
        bucketed: dict[str, list[dict[str, Any]]] = {}
        entity_chunk_map: dict[str, list[str]] = {}
        entity_name_set: set[str] = set()

        for entity in records:
            entity_type = str(entity.get("entity_type", "")).lower()
            name = entity.get("entity_name") or entity.get("name") or ""
            name_lc = str(name).strip().lower()
            if relevant_entity_names is not None:
                if not name_lc or name_lc not in relevant_entity_names:
                    continue
            elif wanted is None and entity_type in self._NOISE_BUCKETS:
                continue
            if wanted and entity_type not in wanted:
                continue

            bucket = bucketed.setdefault(entity_type or "unknown", [])
            if len(bucket) >= max_per_type:
                continue

            raw_src = str(entity.get("source_id") or "")
            chunk_ids = [chunk.strip() for chunk in raw_src.split("<SEP>") if chunk.strip()]
            bucket.append(
                {
                    "name": name,
                    "description": (entity.get("description") or "")[:400],
                    "source_chunks": (
                        chunk_ids[:max_chunks_per_entity]
                        if max_chunks_per_entity > 0
                        else []
                    ),
                }
            )
            if name:
                entity_chunk_map[name] = chunk_ids
                entity_name_set.add(name_lc)

        return {
            "entities": bucketed,
            "source_chunks": self._load_source_chunks(
                entity_chunk_map,
                max_chunks_per_entity,
            ),
            "relationships": self._load_relationships(
                entity_name_set,
                max_relationships_per_entity,
            ),
        }

    def _read_records(self, file_name: str) -> list[dict[str, Any]]:
        """Read one VDB JSON file, normalized to list[dict]."""

        file_path = self.workspace_dir / file_name
        if not file_path.exists():
            return []

        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to read %s for skill context: %s", file_name, exc)
            return []

        if isinstance(raw, dict) and isinstance(raw.get("data"), list):
            return [record for record in raw["data"] if isinstance(record, dict)]
        if isinstance(raw, list):
            return [record for record in raw if isinstance(record, dict)]
        return []

    def _load_source_chunks(
        self,
        entity_chunk_map: dict[str, list[str]],
        max_chunks_per_entity: int,
    ) -> list[dict[str, Any]]:
        wanted_chunk_ids: set[str] = set()
        if max_chunks_per_entity > 0:
            for chunk_ids in entity_chunk_map.values():
                for chunk_id in chunk_ids[:max_chunks_per_entity]:
                    wanted_chunk_ids.add(chunk_id)

        if not wanted_chunk_ids:
            return []

        source_chunks: list[dict[str, Any]] = []
        for record in self._read_records("vdb_chunks.json"):
            chunk_id = record.get("__id__")
            if chunk_id not in wanted_chunk_ids:
                continue
            source_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "file_path": record.get("file_path"),
                    "content": (record.get("content") or "")[:1500],
                }
            )
        return source_chunks

    def _load_relationships(
        self,
        entity_name_set: set[str],
        max_relationships_per_entity: int,
    ) -> list[dict[str, Any]]:
        if max_relationships_per_entity <= 0 or not entity_name_set:
            return []

        relationships: list[dict[str, Any]] = []
        edge_count: dict[str, int] = {name: 0 for name in entity_name_set}
        for record in self._read_records("vdb_relationships.json"):
            source = str(record.get("src_id") or "")
            target = str(record.get("tgt_id") or "")
            source_lc = source.lower()
            target_lc = target.lower()
            source_in = source_lc in entity_name_set
            target_in = target_lc in entity_name_set
            if not (source_in or target_in):
                continue
            if (
                (not source_in or edge_count.get(source_lc, 0) >= max_relationships_per_entity)
                and (not target_in or edge_count.get(target_lc, 0) >= max_relationships_per_entity)
            ):
                continue
            relationships.append(
                {
                    "src": source,
                    "type": str(record.get("keywords") or "").strip(),
                    "tgt": target,
                    "description": (record.get("description") or "")[:300],
                    "source_chunk": record.get("source_id"),
                }
            )
            if source_in:
                edge_count[source_lc] = edge_count.get(source_lc, 0) + 1
            if target_in:
                edge_count[target_lc] = edge_count.get(target_lc, 0) + 1
        return relationships


def build_skill_briefing_book(
    workspace_dir: Path,
    entity_types: Optional[list[str]],
    max_per_type: int,
    max_chunks_per_entity: int = 2,
    max_relationships_per_entity: int = 5,
    relevant_entity_names: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Build the source-grounded briefing book for a skill invocation.

    Returns a dict with three top-level keys:

    * ``entities``: ``{entity_type: [{name, description, source_chunks}]}``
    * ``source_chunks``: verbatim chunk text for cited entities
    * ``relationships``: typed KG edges connected to sliced entities

    ``relevant_entity_names`` is a lowercased whitelist from retrieval. When it
    is present, only matching entities survive; otherwise framework-noise
    buckets are dropped so bulk slices stay focused on solicitation content.
    """
    return SkillWorkspaceEvidenceStore(workspace_dir).build_briefing_book(
        entity_types=entity_types,
        max_per_type=max_per_type,
        max_chunks_per_entity=max_chunks_per_entity,
        max_relationships_per_entity=max_relationships_per_entity,
        relevant_entity_names=relevant_entity_names,
    )


async def retrieve_relevant_entities_for_skill(
    data_func: Optional[QueryDataFunc],
    prompt: str,
    skill_description: str,
    mode: str,
    top_k: int,
) -> dict[str, Any]:
    """Run structured retrieval and return entity and chunk identifiers.

    The return shape is ``{names, chunk_ids, entities, chunks, metadata}``,
    where ``names`` is a lowercased entity-name whitelist, ``chunk_ids`` are
    retrieval-ranked chunks, and ``entities`` / ``chunks`` carry bounded
    summaries callers can surface directly in prompts or UI.
    """
    meta: dict[str, Any] = {
        "mode": mode,
        "top_k": top_k,
        "matched_entities": 0,
        "matched_chunks": 0,
        "used": False,
        "reason": "",
    }
    if mode == "off":
        meta["reason"] = "retrieval disabled (mode=off)"
        return {"names": set(), "chunk_ids": set(), "entities": [], "chunks": [], "metadata": meta}
    if data_func is None:
        meta["reason"] = "server has no data_func; falling back to bulk slice"
        return {"names": set(), "chunk_ids": set(), "entities": [], "chunks": [], "metadata": meta}

    user_prompt = (prompt or "").strip()
    hint = (skill_description or "").strip()
    if not user_prompt and not hint:
        meta["reason"] = "empty prompt + skill description; bulk slice"
        return {"names": set(), "chunk_ids": set(), "entities": [], "chunks": [], "metadata": meta}

    retrieval_query = f"{user_prompt}\n\n[Skill context: {hint}]" if hint else user_prompt
    overrides = {
        "top_k": top_k,
        "chunk_top_k": min(top_k, 30),
        "only_need_context": True,
    }
    try:
        data = await data_func(retrieval_query, mode, [], overrides)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skill retrieval failed (mode=%s): %s", mode, exc)
        meta["reason"] = f"retrieval error: {exc}"
        return {"names": set(), "chunk_ids": set(), "entities": [], "chunks": [], "metadata": meta}

    payload = data.get("data") if isinstance(data, dict) else None
    if not isinstance(payload, dict):
        meta["reason"] = "retrieval returned no data block"
        return {"names": set(), "chunk_ids": set(), "entities": [], "chunks": [], "metadata": meta}

    names, entities = _normalize_retrieved_entities(payload.get("entities") or [], top_k)
    chunk_ids, chunks = _normalize_retrieved_chunks(payload.get("chunks") or [], top_k)

    meta["matched_entities"] = len(names)
    meta["matched_chunks"] = len(chunk_ids)
    meta["used"] = bool(names or chunk_ids)
    if not names and not chunk_ids:
        meta["reason"] = "retrieval returned 0 entities; falling back to bulk slice"
    return {
        "names": names,
        "chunk_ids": chunk_ids,
        "entities": entities,
        "chunks": chunks,
        "metadata": meta,
    }


def _normalize_retrieved_entities(raw_entities: list[Any], top_k: int) -> tuple[set[str], list[dict[str, str]]]:
    names: set[str] = set()
    entities: list[dict[str, str]] = []
    limit = max(1, min(int(top_k or 1), _RETRIEVED_ENTITY_DETAIL_LIMIT))
    for entity in raw_entities:
        if not isinstance(entity, dict):
            continue
        name = entity.get("entity_name") or entity.get("entity_id") or entity.get("name")
        if not name:
            continue
        cleaned_name = str(name).strip()
        if not cleaned_name:
            continue
        lowered = cleaned_name.lower()
        if lowered in names:
            continue
        names.add(lowered)
        detail: dict[str, str] = {"name": cleaned_name}
        entity_type = str(entity.get("entity_type") or entity.get("type") or "").strip()
        summary = _trim_retrieved_text(
            entity.get("description") or entity.get("summary") or entity.get("content") or "",
            _RETRIEVED_SUMMARY_LIMIT,
        )
        if entity_type:
            detail["entity_type"] = entity_type
        if summary:
            detail["summary"] = summary
        entities.append(detail)
        if len(entities) >= limit:
            break
    return names, entities


def _normalize_retrieved_chunks(raw_chunks: list[Any], top_k: int) -> tuple[set[str], list[dict[str, str]]]:
    chunk_ids: set[str] = set()
    chunks: list[dict[str, str]] = []
    limit = max(1, min(int(top_k or 1), _RETRIEVED_CHUNK_DETAIL_LIMIT))
    for chunk in raw_chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_id = chunk.get("chunk_id") or chunk.get("__id__")
        if not chunk_id:
            continue
        cleaned_id = str(chunk_id).strip()
        if not cleaned_id or cleaned_id in chunk_ids:
            continue
        chunk_ids.add(cleaned_id)
        detail: dict[str, str] = {"chunk_id": cleaned_id}
        file_path = str(chunk.get("file_path") or chunk.get("source") or "").strip()
        snippet = _trim_retrieved_text(
            chunk.get("content") or chunk.get("text") or chunk.get("snippet") or "",
            _RETRIEVED_SNIPPET_LIMIT,
        )
        if file_path:
            detail["file_path"] = file_path
        if snippet:
            detail["content"] = snippet
        chunks.append(detail)
        if len(chunks) >= limit:
            break
    return chunk_ids, chunks


def _trim_retrieved_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."
