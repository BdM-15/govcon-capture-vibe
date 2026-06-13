"""Retrieval and deliverable forensics for skill runs (scratchpad, plan, rerank)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Optional

from src.skills.research_plan import match_surface_id

_CHUNK_HEADER_RE = re.compile(r"^####\s+(\S+)", re.MULTILINE)
_PASS_HEADER_RE = re.compile(r"^## Retrieval pass (\d+) — `([^`]+)`", re.MULTILINE)
_QUERY_RE = re.compile(r"^### Query\n(.+?)(?:\n###|\Z)", re.MULTILINE | re.DOTALL)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _parse_scratchpad_passes(scratchpad: str) -> list[dict[str, Any]]:
    if not scratchpad.strip():
        return []
    matches = list(_PASS_HEADER_RE.finditer(scratchpad))
    passes: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(scratchpad)
        block = scratchpad[start:end]
        query_match = _QUERY_RE.search(block)
        query = (query_match.group(1).strip() if query_match else "").strip()
        chunk_ids = _CHUNK_HEADER_RE.findall(block)
        passes.append(
            {
                "pass_num": int(match.group(1)),
                "tool_name": match.group(2),
                "query": query,
                "block_chars": len(block),
                "chunk_ids_in_block": chunk_ids,
                "chunk_count_in_block": len(chunk_ids),
            }
        )
    return passes


def _transcript_kg_stats(transcript: list[dict[str, Any]]) -> dict[str, Any]:
    kg_entities = 0
    kg_chunks = 0
    kg_chunks_skipped = 0
    chunk_ids: list[str] = []
    passes: list[dict[str, Any]] = []
    rerank_scores: list[float] = []
    rerank_skipped = 0

    for entry in transcript:
        if not isinstance(entry, dict) or entry.get("kind") != "tool":
            continue
        name = str(entry.get("name") or "")
        args_raw = entry.get("arguments") or "{}"
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else {}
        except json.JSONDecodeError:
            args = {}
        extra = entry.get("extra") if isinstance(entry.get("extra"), dict) else {}
        if name == "kg_entities":
            kg_entities += 1
            continue
        if name != "kg_chunks":
            continue
        kg_chunks += 1
        query = str(args.get("query") or "")
        plan_guard = extra.get("plan_guard")
        if plan_guard:
            kg_chunks_skipped += 1
        chunk_count = int(extra.get("chunk_count") or 0)
        stored_ids = entry.get("chunk_ids") or []
        if isinstance(stored_ids, list):
            for chunk_id in stored_ids:
                if isinstance(chunk_id, str) and chunk_id:
                    chunk_ids.append(chunk_id)
        rerank = extra.get("rerank") if isinstance(extra.get("rerank"), dict) else {}
        if rerank.get("skipped"):
            rerank_skipped += 1
        top_score = rerank.get("top_score")
        if isinstance(top_score, (int, float)):
            rerank_scores.append(float(top_score))
        passes.append(
            {
                "query": query,
                "chunk_count": chunk_count,
                "plan_guard": plan_guard,
                "chunk_ids_sample": [str(value) for value in stored_ids[:8] if value],
                "rerank": rerank,
            }
        )

    unique_ids = sorted(set(chunk_ids))
    total_seen = len(chunk_ids)
    overlap_rate = 0.0
    if total_seen > 0:
        overlap_rate = round(1.0 - (len(unique_ids) / total_seen), 4)

    rerank_summary: dict[str, Any] = {
        "passes_with_rerank_stats": len(rerank_scores),
        "passes_rerank_skipped": rerank_skipped,
    }
    if rerank_scores:
        rerank_summary.update(
            {
                "top_score_min": round(min(rerank_scores), 4),
                "top_score_max": round(max(rerank_scores), 4),
                "top_score_avg": round(sum(rerank_scores) / len(rerank_scores), 4),
            }
        )

    return {
        "kg_entities_calls": kg_entities,
        "kg_chunks_calls": kg_chunks,
        "kg_chunks_skipped": kg_chunks_skipped,
        "chunk_ids_seen": total_seen,
        "unique_chunk_ids_from_transcript": len(unique_ids),
        "dedup_overlap_rate": overlap_rate,
        "kg_chunks_passes": passes,
        "rerank_summary": rerank_summary,
    }


def _surface_forensics(
    harness_state: dict[str, Any],
    scratchpad_passes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    surfaces = harness_state.get("plan_surfaces") or []
    if not isinstance(surfaces, list):
        return []
    rows: list[dict[str, Any]] = []
    for surface in surfaces:
        if not isinstance(surface, dict):
            continue
        surface_id = str(surface.get("id") or "")
        matched_passes = []
        for item in scratchpad_passes:
            if item.get("tool_name") != "kg_chunks":
                continue
            query = str(item.get("query") or "")
            if match_surface_id(query, [surface]) == surface_id:
                matched_passes.append(item)
        block_chars = sum(int(item.get("block_chars") or 0) for item in matched_passes)
        chunk_ids: set[str] = set()
        for item in matched_passes:
            for chunk_id in item.get("chunk_ids_in_block") or []:
                chunk_ids.add(str(chunk_id))
        rows.append(
            {
                "surface_id": surface_id,
                "label": surface.get("label"),
                "status": surface.get("status"),
                "inquiry": surface.get("inquiry"),
                "shipley": surface.get("shipley"),
                "feeds": surface.get("feeds"),
                "kg_chunks_attempts": int(surface.get("kg_chunks_attempts") or 0),
                "last_new_chunks": int(surface.get("last_new_chunks") or 0),
                "scratchpad_chars": block_chars,
                "unique_chunks_in_scratchpad": len(chunk_ids),
                "matched_pass_count": len(matched_passes),
            }
        )
    return rows


def _frame_counts(frame: Mapping[str, Any] | None) -> dict[str, int]:
    if not frame:
        return {}
    keys = (
        "customer_pain_points",
        "eval_crosswalk",
        "win_theme_candidates",
        "innovation_opportunities",
        "current_methods",
        "importance_signals",
        "implicit_criteria",
        "verbatim_extracts",
    )
    counts: dict[str, int] = {}
    for key in keys:
        value = frame.get(key)
        counts[key] = len(value) if isinstance(value, list) else 0
    return counts


def build_run_forensics(run_dir: Path) -> dict[str, Any]:
    """Assemble retrieval/deliverable forensics for one skill run directory."""
    run_path = Path(run_dir)
    artifacts = run_path / "artifacts"
    transcript = _read_json(run_path / "transcript.json")
    transcript_list = transcript if isinstance(transcript, list) else []

    scratchpad_text = _read_text(artifacts / "research_scratchpad.md")
    scratchpad_passes = _parse_scratchpad_passes(scratchpad_text)
    harness_state = _read_json(artifacts / "harness_state.json") or {}
    retrieval_plan = _read_json(artifacts / "retrieval_plan.json") or {}
    frame = _read_json(artifacts / "mission_readiness_frame.json")
    if not isinstance(frame, dict):
        frame = _read_json(artifacts / "frame.json")
    brief_text = _read_text(artifacts / "brief.md")

    scratchpad_chunk_ids = harness_state.get("scratchpad_chunk_ids") or []
    unique_scratchpad_ids = (
        len({str(item) for item in scratchpad_chunk_ids if item})
        if isinstance(scratchpad_chunk_ids, list)
        else 0
    )

    transcript_stats = _transcript_kg_stats(transcript_list)
    surface_rows = _surface_forensics(
        harness_state if isinstance(harness_state, dict) else {},
        scratchpad_passes,
    )

    all_scratchpad_chunk_ids: set[str] = set()
    for item in scratchpad_passes:
        for chunk_id in item.get("chunk_ids_in_block") or []:
            all_scratchpad_chunk_ids.add(str(chunk_id))

    return {
        "run_dir": str(run_path),
        "scratchpad": {
            "chars": len(scratchpad_text),
            "retrieval_pass_sections": len(scratchpad_passes),
            "unique_chunk_ids_in_scratchpad": len(all_scratchpad_chunk_ids),
            "unique_chunk_ids_tracked_in_state": unique_scratchpad_ids,
        },
        "harness": {
            "phase": harness_state.get("phase") if isinstance(harness_state, dict) else None,
            "plan_complete": bool(retrieval_plan.get("plan_complete")),
            "kg_entities_satisfied": bool(
                harness_state.get("kg_entities_satisfied") if isinstance(harness_state, dict) else False
            ),
            "kg_chunks_calls_state": int(
                harness_state.get("kg_chunks_calls") or 0
            ) if isinstance(harness_state, dict) else 0,
        },
        "transcript_retrieval": transcript_stats,
        "surfaces": surface_rows,
        "deliverables": {
            "brief_chars": len(brief_text),
            "brief_lines": len(brief_text.splitlines()) if brief_text else 0,
            "frame_counts": _frame_counts(frame if isinstance(frame, dict) else None),
        },
        "rerank_tuning_hints": _rerank_tuning_hints(transcript_stats.get("kg_chunks_passes") or []),
    }


def _rerank_tuning_hints(passes: list[dict[str, Any]]) -> list[str]:
    """Heuristic notes to inform future dynamic rerank thresholds."""
    hints: list[str] = []
    low_confidence = 0
    high_confidence = 0
    skipped = 0
    for item in passes:
        if not isinstance(item, dict):
            continue
        if item.get("plan_guard"):
            continue
        rerank = item.get("rerank") if isinstance(item.get("rerank"), dict) else {}
        if rerank.get("skipped"):
            skipped += 1
            continue
        top_score = rerank.get("top_score")
        if not isinstance(top_score, (int, float)):
            hints.append(
                "Some kg_chunks passes lack rerank stats in transcript — upgrade server "
                "and re-run to populate top_score for tuning."
            )
            return hints
        if float(top_score) < 0.25:
            low_confidence += 1
        elif float(top_score) >= 0.65:
            high_confidence += 1
    if low_confidence:
        hints.append(
            f"{low_confidence} pass(es) had rerank top_score < 0.25 — cross-encoder likely helped ordering."
        )
    if high_confidence:
        hints.append(
            f"{high_confidence} pass(es) had rerank top_score >= 0.65 — candidate for rerank skip experiments."
        )
    if skipped:
        hints.append(f"{skipped} pass(es) recorded rerank_skipped (candidates <= chunk_top_k).")
    if not hints:
        hints.append("Insufficient rerank stats yet — run after server restart with forensics capture enabled.")
    return hints


def format_run_forensics_report(payload: Mapping[str, Any]) -> str:
    """Human-readable forensics summary for CLI / logs."""
    lines = [
        "=== Retrieval forensics ===",
        f"run_dir: {payload.get('run_dir')}",
    ]
    scratchpad = payload.get("scratchpad") or {}
    lines.append(
        "scratchpad: "
        f"{scratchpad.get('chars', 0)} chars | "
        f"{scratchpad.get('retrieval_pass_sections', 0)} passes | "
        f"{scratchpad.get('unique_chunk_ids_in_scratchpad', 0)} unique chunks"
    )
    harness = payload.get("harness") or {}
    lines.append(
        "harness: "
        f"phase={harness.get('phase')} plan_complete={harness.get('plan_complete')} "
        f"kg_entities_ok={harness.get('kg_entities_satisfied')}"
    )
    transcript = payload.get("transcript_retrieval") or {}
    lines.append(
        "transcript: "
        f"kg_entities={transcript.get('kg_entities_calls', 0)} "
        f"kg_chunks={transcript.get('kg_chunks_calls', 0)} "
        f"skipped={transcript.get('kg_chunks_skipped', 0)} "
        f"unique_chunks={transcript.get('unique_chunk_ids_from_transcript', 0)} "
        f"dedup_overlap={transcript.get('dedup_overlap_rate', 0)}"
    )
    rerank = transcript.get("rerank_summary") or {}
    if rerank:
        lines.append(
            "rerank: "
            f"stats={rerank.get('passes_with_rerank_stats', 0)} "
            f"skipped={rerank.get('passes_rerank_skipped', 0)} "
            f"top_score_avg={rerank.get('top_score_avg', 'n/a')} "
            f"min={rerank.get('top_score_min', 'n/a')} "
            f"max={rerank.get('top_score_max', 'n/a')}"
        )
    lines.append("surfaces:")
    for row in payload.get("surfaces") or []:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"  - {row.get('surface_id')}: status={row.get('status')} "
            f"scratchpad_chars={row.get('scratchpad_chars', 0)} "
            f"unique_chunks={row.get('unique_chunks_in_scratchpad', 0)} "
            f"last_new={row.get('last_new_chunks', 0)}"
        )
    deliverables = payload.get("deliverables") or {}
    lines.append(
        f"brief: {deliverables.get('brief_lines', 0)} lines / {deliverables.get('brief_chars', 0)} chars"
    )
    frame_counts = deliverables.get("frame_counts") or {}
    if frame_counts:
        lines.append("frame_counts: " + ", ".join(f"{key}={value}" for key, value in frame_counts.items()))
    hints = payload.get("rerank_tuning_hints") or []
    if hints:
        lines.append("rerank_tuning_hints:")
        for hint in hints:
            lines.append(f"  - {hint}")
    return "\n".join(lines)


def write_run_forensics(run_dir: Path, *, emit_json: bool = True) -> dict[str, Any]:
    """Build forensics payload and optionally write artifacts/retrieval_forensics.json."""
    payload = build_run_forensics(run_dir)
    if emit_json:
        out_path = Path(run_dir) / "artifacts" / "retrieval_forensics.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["forensics_path"] = str(out_path)
    return payload