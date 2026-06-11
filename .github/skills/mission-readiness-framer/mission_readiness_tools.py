"""Deterministic helpers for mission-readiness-framer Studio deliverables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _join_list(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, (str, int, float, bool)):
                parts.append(str(item))
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        return ", ".join(parts)
    return str(value)


def build_workbook_payload(envelope: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Flatten the skill envelope into workbook-friendly top-level arrays."""
    if not isinstance(envelope, dict):
        return {"frame_summary": []}

    frame = envelope.get("mission_readiness_frame") or {}
    context = envelope.get("opportunity_context") or {}

    frame_summary = [
        {
            "solicitation_id": context.get("solicitation_id"),
            "agency": context.get("agency"),
            "readiness_outcome": frame.get("readiness_outcome"),
            "confidence": frame.get("confidence"),
            "our_read": frame.get("our_read"),
            "failure_modes_feared": _join_list(frame.get("failure_modes_feared")),
            "source_chunk_ids": _join_list(frame.get("source_chunk_ids")),
        }
    ]

    return {
        "frame_summary": frame_summary,
        "workload_enablers": list(frame.get("workload_enablers") or []),
        "readiness_signals": list(frame.get("readiness_signals") or []),
        "customer_pain_points": list(envelope.get("customer_pain_points") or []),
        "importance_signals": list(envelope.get("importance_signals") or []),
        "implicit_criteria": list(envelope.get("implicit_criteria") or []),
        "win_theme_candidates": list(envelope.get("win_theme_candidates") or []),
        "verbatim_extracts": list(envelope.get("verbatim_extracts") or []),
        "eval_crosswalk": list(envelope.get("eval_crosswalk") or []),
        "clarification_questions": list(envelope.get("clarification_questions") or []),
        "claim_gaps": [
            {"gap": gap}
            for gap in (envelope.get("claim_gaps") or [])
            if str(gap).strip()
        ],
    }


def write_workbook_source(artifacts_dir: Path, envelope: dict[str, Any]) -> Path | None:
    """Write mission_readiness_workbook.json for render_xlsx when frame JSON exists."""
    source = artifacts_dir / "mission_readiness_frame.json"
    if not source.is_file():
        return None
    payload = envelope if envelope else json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    out = artifacts_dir / "mission_readiness_workbook.json"
    out.write_text(
        json.dumps(build_workbook_payload(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out