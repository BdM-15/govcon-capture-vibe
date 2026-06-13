"""Rich grounded-context retrieval for researcher artifacts via LightRAG aquery_data."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

QueryDataFunc = Callable[[str, str, list[dict], dict], Awaitable[dict]]


def build_retrieval_query(prompt: str, skill_description: str) -> str:
    """Compose the hybrid retrieval query from user prompt + skill description."""
    user_prompt = (prompt or "").strip()
    hint = (skill_description or "").strip()
    if not user_prompt and not hint:
        return ""
    if hint:
        return f"{user_prompt}\n\n[Skill context: {hint}]" if user_prompt else hint
    return user_prompt


def _normalize_entity_name(entity: dict[str, Any]) -> str:
    name = entity.get("entity_name") or entity.get("entity_id") or entity.get("name")
    return str(name).strip().lower() if name else ""


def _normalize_chunk_id(chunk: dict[str, Any]) -> str:
    chunk_id = chunk.get("chunk_id") or chunk.get("__id__")
    return str(chunk_id).strip() if chunk_id else ""


def shape_grounded_payload(
    raw: dict[str, Any],
    *,
    top_k: int,
) -> dict[str, Any]:
    """Normalize aquery_data response into a researcher artifact payload."""
    payload = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(payload, dict):
        return {
            "entities": [],
            "relationships": [],
            "chunks": [],
            "references": [],
            "names": set(),
            "chunk_ids": set(),
            "status": raw.get("status") if isinstance(raw, dict) else None,
            "message": raw.get("message") if isinstance(raw, dict) else "",
        }

    entities = [
        item for item in (payload.get("entities") or []) if isinstance(item, dict)
    ]
    relationships = [
        item for item in (payload.get("relationships") or []) if isinstance(item, dict)
    ]
    chunks = [item for item in (payload.get("chunks") or []) if isinstance(item, dict)]
    references = [
        item for item in (payload.get("references") or []) if isinstance(item, dict)
    ]

    names: set[str] = set()
    for entity in entities:
        name_lc = _normalize_entity_name(entity)
        if name_lc:
            names.add(name_lc)
    if len(names) > top_k:
        names = set(list(names)[:top_k])

    chunk_ids: set[str] = set()
    for chunk in chunks:
        chunk_id = _normalize_chunk_id(chunk)
        if chunk_id:
            chunk_ids.add(chunk_id)

    return {
        "entities": entities,
        "relationships": relationships,
        "chunks": chunks,
        "references": references,
        "names": names,
        "chunk_ids": chunk_ids,
        "status": raw.get("status"),
        "message": raw.get("message") or "",
    }


def format_grounded_context_for_scratchpad(
    grounded: dict[str, Any],
    *,
    query: str = "",
    max_chars: int = 48_000,
) -> str:
    """Format full grounded payload as markdown for research scratchpad seeding."""
    lines = ["## Bootstrap retrieval (aquery_data)\n"]
    if query.strip():
        lines.append(f"### Query\n{query.strip()}\n")

    entities = grounded.get("entities") or []
    if entities:
        lines.append("### Ranked entities")
        budget = max_chars
        for entity in entities[:80]:
            if not isinstance(entity, dict):
                continue
            name = (
                entity.get("entity_name")
                or entity.get("entity_id")
                or entity.get("name")
                or ""
            )
            entity_type = str(entity.get("entity_type") or "").strip()
            description = str(entity.get("description") or "").strip()[:800]
            snippet = f"- **{name}** ({entity_type}): {description}".strip()
            lines.append(snippet)
            budget -= len(snippet)
            if budget <= 0:
                lines.append("…[entity list truncated]")
                break

    relationships = grounded.get("relationships") or []
    if relationships:
        lines.append("\n### Ranked relationships")
        budget = max(5000, max_chars // 4)
        for rel in relationships[:60]:
            if not isinstance(rel, dict):
                continue
            src = rel.get("src_id") or rel.get("src") or ""
            tgt = rel.get("tgt_id") or rel.get("tgt") or ""
            desc = str(rel.get("description") or rel.get("keywords") or "")[:300]
            snippet = f"- {src} → {tgt}: {desc}"
            lines.append(snippet)
            budget -= len(snippet)
            if budget <= 0:
                lines.append("…[relationship list truncated]")
                break

    chunks = grounded.get("chunks") or []
    if chunks:
        lines.append("\n### Ranked source excerpts")
        budget = max_chars // 2
        for chunk in chunks[:40]:
            if not isinstance(chunk, dict):
                continue
            chunk_id = _normalize_chunk_id(chunk)
            content = str(chunk.get("content") or "").strip()
            if not content:
                continue
            excerpt = content[: min(3000, budget)]
            lines.append(f"\n#### {chunk_id or 'chunk'}\n{excerpt}")
            budget -= len(excerpt)
            if budget <= 0:
                lines.append("…[chunk excerpts truncated]")
                break

    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[:max_chars] + "\n…[bootstrap context truncated]\n"
    return text + "\n"


async def retrieve_grounded_context_for_researcher_artifact(
    data_func: Optional[QueryDataFunc],
    *,
    prompt: str,
    skill_description: str,
    mode: str,
    query_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Wrap aquery_data and return full ranked grounded context + compat keys."""
    top_k = int(query_overrides.get("top_k") or 40)
    meta: dict[str, Any] = {
        "mode": mode,
        "top_k": top_k,
        "chunk_top_k": query_overrides.get("chunk_top_k"),
        "max_total_tokens": query_overrides.get("max_total_tokens"),
        "matched_entities": 0,
        "matched_chunks": 0,
        "matched_relationships": 0,
        "used": False,
        "reason": "",
        "query_overrides": {
            key: query_overrides[key]
            for key in (
                "top_k",
                "chunk_top_k",
                "max_entity_tokens",
                "max_relation_tokens",
                "max_total_tokens",
                "enable_rerank",
            )
            if key in query_overrides
        },
    }

    if mode == "off":
        meta["reason"] = "retrieval disabled (mode=off)"
        return _empty_result(meta)

    if data_func is None:
        meta["reason"] = "server has no data_func; falling back to bulk slice"
        return _empty_result(meta)

    retrieval_query = build_retrieval_query(prompt, skill_description)
    if not retrieval_query:
        meta["reason"] = "empty prompt + skill description; bulk slice"
        return _empty_result(meta)

    overrides = dict(query_overrides)
    overrides.setdefault("only_need_context", True)
    try:
        raw = await data_func(retrieval_query, mode, [], overrides)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Grounded retrieval failed (mode=%s): %s", mode, exc)
        meta["reason"] = f"retrieval error: {exc}"
        return _empty_result(meta)

    shaped = shape_grounded_payload(raw, top_k=top_k)
    meta["matched_entities"] = len(shaped.get("entities") or [])
    meta["matched_chunks"] = len(shaped.get("chunk_ids") or set())
    meta["matched_relationships"] = len(shaped.get("relationships") or [])
    meta["used"] = bool(
        shaped.get("entities") or shaped.get("chunk_ids") or shaped.get("relationships")
    )
    if not meta["used"]:
        meta["reason"] = "retrieval returned 0 entities/chunks/relationships"
    meta["retrieval_query"] = retrieval_query
    return {**shaped, "metadata": meta}


def _empty_result(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "entities": [],
        "relationships": [],
        "chunks": [],
        "references": [],
        "names": set(),
        "chunk_ids": set(),
        "metadata": meta,
    }