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
        retrieval_chunk_ids: Optional[set[str]] = None,
        max_chunk_content_chars: int = 8000,
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
            entity_type = str(entity.get("entity_type") or "").lower()
            name = (
                entity.get("entity_name")
                or entity.get("entity_id")
                or entity.get("name")
                or ""
            )
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
                retrieval_chunk_ids=retrieval_chunk_ids,
                max_chunk_content_chars=max_chunk_content_chars,
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
        *,
        retrieval_chunk_ids: Optional[set[str]] = None,
        max_chunk_content_chars: int = 8000,
    ) -> list[dict[str, Any]]:
        wanted_chunk_ids: set[str] = set(retrieval_chunk_ids or [])
        if max_chunks_per_entity > 0:
            for chunk_ids in entity_chunk_map.values():
                for chunk_id in chunk_ids[:max_chunks_per_entity]:
                    wanted_chunk_ids.add(chunk_id)

        if not wanted_chunk_ids:
            return []

        source_chunks: list[dict[str, Any]] = []
        content_cap = max(500, int(max_chunk_content_chars or 8000))
        for record in self._read_records("vdb_chunks.json"):
            chunk_id = record.get("__id__")
            if chunk_id not in wanted_chunk_ids:
                continue
            content = str(record.get("content") or "")
            truncated = len(content) > content_cap
            source_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "file_path": record.get("file_path"),
                    "content": content[:content_cap],
                    "truncated": truncated,
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
    retrieval_chunk_ids: Optional[set[str]] = None,
    max_chunk_content_chars: int = 8000,
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
        retrieval_chunk_ids=retrieval_chunk_ids,
        max_chunk_content_chars=max_chunk_content_chars,
    )


async def retrieve_relevant_entities_for_skill(
    data_func: Optional[QueryDataFunc],
    prompt: str,
    skill_description: str,
    *,
    mode: str,
    query_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Run structured retrieval and return full grounded context + compat keys.

    Return shape includes ``names``, ``chunk_ids``, ``metadata`` (backward
    compatible), plus ``entities``, ``relationships``, ``chunks``,
    ``references`` from the full ``aquery_data`` payload.
    """
    from src.skills.researcher_retrieval import (
        retrieve_grounded_context_for_researcher_artifact,
    )

    grounded = await retrieve_grounded_context_for_researcher_artifact(
        data_func,
        prompt=prompt,
        skill_description=skill_description,
        mode=mode,
        query_overrides=query_overrides,
    )
    return {
        "names": grounded.get("names") or set(),
        "chunk_ids": grounded.get("chunk_ids") or set(),
        "entities": grounded.get("entities") or [],
        "relationships": grounded.get("relationships") or [],
        "chunks": grounded.get("chunks") or [],
        "references": grounded.get("references") or [],
        "metadata": grounded.get("metadata") or {},
    }