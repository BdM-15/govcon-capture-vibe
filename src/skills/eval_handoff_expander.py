"""Batched platform expansion for readiness-frame-eval crosswalk coverage."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.skills.evidence_gates import (
    check_coverage_contract,
    is_material_eval_factor,
    load_material_eval_entities,
)
from src.skills.handoff_quality import _EVAL_COVERAGE_CONTRACT
from src.skills.llm_chat import chat_with_tools
from src.skills.readiness_handoff_models import EvalCrosswalkRow, load_handoff_dict
from src.skills.research_harness import _extract_json_object, _read_artifact

logger = logging.getLogger(__name__)

_BATCH_SIZE = 8
_MAX_BATCHES = 10


def _existing_labels(payload: dict[str, Any]) -> set[str]:
    crosswalk = payload.get("eval_crosswalk") or []
    if not isinstance(crosswalk, list):
        return set()
    return {
        str(row.get("evaluation_factor") or "").strip().lower()
        for row in crosswalk
        if isinstance(row, dict) and str(row.get("evaluation_factor") or "").strip()
    }


def _missing_entities(
    workspace_dir: Path,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    existing = _existing_labels(payload)
    missing: list[dict[str, Any]] = []
    for entity in load_material_eval_entities(workspace_dir):
        name = str(entity.get("name") or "").strip()
        if not name or name.lower() in existing:
            continue
        missing.append(entity)
    return missing


def _normalize_crosswalk_rows(rows: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            normalized.append(EvalCrosswalkRow.from_legacy(row).model_dump())
        except Exception:  # noqa: BLE001
            continue
    return normalized


def _scratchpad_grounded_chunk_ids(scratchpad: str) -> set[str]:
    return set(re.findall(r"(?:doc-|chunk-|tb-)[a-zA-Z0-9_-]+", scratchpad or "", re.IGNORECASE))


def _known_factor_labels(workspace_dir: Path | None) -> set[str]:
    if workspace_dir is None:
        return set()
    return {
        str(entity.get("name") or "").strip().lower()
        for entity in load_material_eval_entities(workspace_dir)
        if str(entity.get("name") or "").strip()
    }


def _factor_matches_inventory(label: str, known: set[str]) -> bool:
    normalized = str(label or "").strip().lower()
    if not normalized or not known:
        return bool(normalized and is_material_eval_factor(normalized))
    if normalized in known:
        return True
    return any(
        normalized in known_label or known_label in normalized for known_label in known
    )


def _ground_crosswalk_to_scratchpad(
    payload: dict[str, Any],
    scratchpad: str,
) -> dict[str, Any]:
    """Drop invented chunk IDs — keep only IDs that appear in retrieved evidence."""
    grounded_ids = _scratchpad_grounded_chunk_ids(scratchpad)
    crosswalk = payload.get("eval_crosswalk") or []
    if not isinstance(crosswalk, list):
        return payload
    for row in crosswalk:
        if not isinstance(row, dict):
            continue
        chunk_ids = row.get("source_chunk_ids") or []
        if not isinstance(chunk_ids, list):
            continue
        row["source_chunk_ids"] = [
            str(item).strip()
            for item in chunk_ids
            if str(item).strip() in grounded_ids
        ]
    payload["eval_crosswalk"] = crosswalk
    return payload


def prune_ungrounded_crosswalk_rows(
    payload: dict[str, Any],
    *,
    scratchpad: str,
    workspace_dir: Path | None,
) -> dict[str, Any]:
    """Drop invented factor names and rows that lost all scratchpad chunk IDs."""
    payload = _ground_crosswalk_to_scratchpad(payload, scratchpad)
    known = _known_factor_labels(workspace_dir)
    crosswalk = payload.get("eval_crosswalk") or []
    gaps = payload.get("claim_gaps")
    if not isinstance(gaps, list):
        gaps = []
    if not isinstance(crosswalk, list):
        return payload

    kept: list[dict[str, Any]] = []
    for row in crosswalk:
        if not isinstance(row, dict):
            continue
        factor = str(row.get("evaluation_factor") or "").strip()
        if not factor:
            continue
        if known and not _factor_matches_inventory(factor, known):
            gap = f"eval_crosswalk: dropped invented factor {factor!r}"
            if gap not in gaps:
                gaps.append(gap)
            continue
        chunk_ids = row.get("source_chunk_ids") or []
        if not isinstance(chunk_ids, list) or not any(str(item).strip() for item in chunk_ids):
            gap = f"eval_crosswalk: ungrounded row for {factor} — no scratchpad chunk IDs"
            if gap not in gaps:
                gaps.append(gap)
            continue
        kept.append(row)

    payload["eval_crosswalk"] = kept
    payload["claim_gaps"] = gaps
    return payload


def _normalize_payload_crosswalk(payload: dict[str, Any]) -> dict[str, Any]:
    crosswalk = payload.get("eval_crosswalk") or []
    if isinstance(crosswalk, list):
        payload["eval_crosswalk"] = _normalize_crosswalk_rows(crosswalk)
    return payload


def _diversify_crosswalk_primary_chunks(payload: dict[str, Any]) -> dict[str, Any]:
    """Rotate over-used primary source_chunk_ids when rows carry alternates."""
    crosswalk = payload.get("eval_crosswalk") or []
    if not isinstance(crosswalk, list) or len(crosswalk) < 8:
        return payload

    primaries: list[str] = []
    for row in crosswalk:
        if not isinstance(row, dict):
            continue
        chunk_ids = row.get("source_chunk_ids") or []
        if isinstance(chunk_ids, list) and chunk_ids:
            primary = str(chunk_ids[0] or "").strip()
            if primary:
                primaries.append(primary)
    if len(primaries) < 8:
        return payload

    counts: dict[str, int] = {}
    for chunk_id in primaries:
        counts[chunk_id] = counts.get(chunk_id, 0) + 1
    top_chunk, top_count = max(counts.items(), key=lambda item: item[1])
    if top_count / len(primaries) <= 0.45:
        return payload

    usage = dict(counts)
    for row in crosswalk:
        if not isinstance(row, dict):
            continue
        chunk_ids = row.get("source_chunk_ids") or []
        if not isinstance(chunk_ids, list) or len(chunk_ids) < 2:
            continue
        primary = str(chunk_ids[0] or "").strip()
        if primary != top_chunk:
            continue
        replacement = next(
            (
                str(item).strip()
                for item in chunk_ids[1:]
                if str(item).strip() and usage.get(str(item).strip(), 0) < top_count // 2
            ),
            "",
        )
        if not replacement:
            continue
        row["source_chunk_ids"] = [replacement] + [
            cid for cid in chunk_ids if str(cid).strip() != replacement
        ]
        usage[primary] = max(0, usage.get(primary, 0) - 1)
        usage[replacement] = usage.get(replacement, 0) + 1

    payload["eval_crosswalk"] = crosswalk
    return payload


def _merge_rows(payload: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    crosswalk = payload.get("eval_crosswalk")
    if not isinstance(crosswalk, list):
        crosswalk = []
    gaps = payload.get("claim_gaps")
    if not isinstance(gaps, list):
        gaps = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("evaluation_factor") or "").strip()
        if not label:
            continue
        if label.lower() in _existing_labels(payload):
            continue
        normalized_rows = _normalize_crosswalk_rows([row])
        if not normalized_rows:
            continue
        crosswalk.append(normalized_rows[0])
        existing = f"eval_crosswalk: missing row for {label}"
        if existing in gaps:
            gaps = [gap for gap in gaps if str(gap) != existing]
    payload["eval_crosswalk"] = crosswalk
    payload["claim_gaps"] = gaps
    return payload


def _build_batch_messages(
    *,
    entities: list[dict[str, Any]],
    scratchpad: str,
    existing_count: int,
) -> list[dict[str, str]]:
    inventory = "\n".join(
        f"- {entity.get('name')} ({entity.get('entity_type')})"
        for entity in entities
    )
    system = (
        "You expand eval_crosswalk[] rows for readiness-frame-eval on Project Theseus.\n"
        "Use ONLY scratchpad evidence. Return ONE JSON object:\n"
        '{"eval_crosswalk":[...], "claim_gaps":[]}\n'
        "Each row needs evaluation_factor (verbatim batch entity name), pws_clusters[], "
        "readiness_link (>=60 chars), proof_expected (>=30 chars), source_chunk_ids[] "
        "with real chunk/doc/tb IDs from scratchpad.\n"
        "Rows without scratchpad chunk IDs are dropped — put ungrounded entities in claim_gaps[].\n"
        "No invented factor labels. No boilerplate. One row per factor in this batch only."
    )
    user = (
        f"## Batch entities ({len(entities)})\n{inventory}\n\n"
        f"## Existing crosswalk rows so far: {existing_count}\n\n"
        f"## Research scratchpad\n{scratchpad or '(empty)'}\n\n"
        "Emit eval_crosswalk rows for every batch entity you can ground. "
        "Put ungrounded entity names in claim_gaps[] only."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def expand_eval_handoff(
    *,
    run_dir: Path,
    workspace_dir: Path,
    loop_response: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """Grow eval_handoff.json until coverage contract passes or batch budget exhausts."""
    warnings: list[str] = []
    artifacts = Path(run_dir) / "artifacts"
    handoff_path = artifacts / "eval_handoff.json"

    payload: dict[str, Any] = {"eval_crosswalk": [], "claim_gaps": []}
    if handoff_path.is_file():
        try:
            payload = load_handoff_dict(handoff_path)
        except (OSError, json.JSONDecodeError, ValueError):
            warnings.append("eval_handoff_expander: unreadable existing handoff; rebuilding")

    if not payload.get("eval_crosswalk") and loop_response.strip():
        parsed = _extract_json_object(loop_response)
        if isinstance(parsed, dict):
            payload = parsed

    scratchpad = _read_artifact(Path(run_dir), "research_scratchpad.md", max_chars=180_000)
    batch_index = 0

    while batch_index < _MAX_BATCHES:
        issues = check_coverage_contract(
            workspace_dir=workspace_dir,
            coverage_contract=_EVAL_COVERAGE_CONTRACT,
            artifact=payload,
        )
        if not issues:
            break

        missing = _missing_entities(workspace_dir, payload)
        if not missing:
            break

        batch = missing[:_BATCH_SIZE]
        batch_index += 1
        messages = _build_batch_messages(
            entities=batch,
            scratchpad=scratchpad,
            existing_count=len(payload.get("eval_crosswalk") or []),
        )
        try:
            chat = await chat_with_tools(
                messages=messages,
                tools=None,
                temperature=0.2,
                max_tokens=16_000,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("eval_handoff batch %d failed: %s", batch_index, exc)
            warnings.append(f"eval_handoff_expander: batch {batch_index} LLM error: {exc}")
            break

        parsed = _extract_json_object(chat.content or "")
        if not isinstance(parsed, dict):
            warnings.append(
                f"eval_handoff_expander: batch {batch_index} returned unparsable JSON"
            )
            continue

        rows = parsed.get("eval_crosswalk") or []
        if isinstance(rows, list) and rows:
            before = len(_existing_labels(payload))
            payload = _ground_crosswalk_to_scratchpad(payload, scratchpad)
            filtered_rows = []
            known = _known_factor_labels(workspace_dir)
            grounded_ids = _scratchpad_grounded_chunk_ids(scratchpad)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                factor = str(row.get("evaluation_factor") or "").strip()
                if known and factor and not _factor_matches_inventory(factor, known):
                    continue
                chunk_ids = row.get("source_chunk_ids") or []
                if not isinstance(chunk_ids, list):
                    continue
                row["source_chunk_ids"] = [
                    str(item).strip()
                    for item in chunk_ids
                    if str(item).strip() in grounded_ids
                ]
                if row["source_chunk_ids"]:
                    filtered_rows.append(row)
            payload = _merge_rows(payload, filtered_rows)
            after = len(_existing_labels(payload))
            warnings.append(
                f"eval_handoff_expander: batch {batch_index} added {after - before} rows"
            )

        extra_gaps = parsed.get("claim_gaps") or []
        if isinstance(extra_gaps, list):
            gaps = payload.get("claim_gaps")
            if not isinstance(gaps, list):
                gaps = []
            for gap in extra_gaps:
                text = str(gap or "").strip()
                if text and text not in gaps:
                    gaps.append(text)
            payload["claim_gaps"] = gaps

    from src.skills.source_citations import enrich_payload_citations

    payload = _normalize_payload_crosswalk(payload)
    payload = _ground_crosswalk_to_scratchpad(payload, scratchpad)
    payload = prune_ungrounded_crosswalk_rows(
        payload,
        scratchpad=scratchpad,
        workspace_dir=workspace_dir,
    )
    payload = enrich_payload_citations(payload, workspace_dir)
    payload = _normalize_payload_crosswalk(payload)
    payload = _ground_crosswalk_to_scratchpad(payload, scratchpad)
    payload = prune_ungrounded_crosswalk_rows(
        payload,
        scratchpad=scratchpad,
        workspace_dir=workspace_dir,
    )
    payload = _diversify_crosswalk_primary_chunks(payload)
    artifacts.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    warnings.append(
        f"eval_handoff_expander: wrote eval_handoff.json with "
        f"{len(payload.get('eval_crosswalk') or [])} rows"
    )
    return payload, warnings