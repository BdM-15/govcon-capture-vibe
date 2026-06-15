"""Deterministic pre-gate repair for readiness-frame-eval handoffs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.skills.evidence_gates import crosswalk_material_row_labels
from src.skills.readiness_content_gates import apply_known_acronym_expansions_to_eval_payload
from src.skills.readiness_handoff_models import load_handoff_dict

logger = logging.getLogger(__name__)

_GAP_TEMPLATE = "Material factor {label} — no grounded chunk evidence after batch retrieval"


def _manifest_factor_labels(run_dir: Path) -> list[str]:
    manifest_path = Path(run_dir) / "artifacts" / "eval_batch_manifest.json"
    if not manifest_path.is_file():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    labels: list[str] = []
    seen: set[str] = set()
    for batch in data.get("batches") or []:
        if not isinstance(batch, dict):
            continue
        for raw in batch.get("factors") or []:
            label = str(raw or "").strip()
            if not label:
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            labels.append(label)
    return labels


def sync_eval_claim_gaps_from_manifest(payload: dict[str, Any], *, run_dir: Path) -> dict[str, Any]:
    """Append verbatim manifest factor names missing from rows or claim_gaps[]."""
    inventory = _manifest_factor_labels(run_dir)
    if not inventory:
        return payload

    crosswalk = payload.get("eval_crosswalk") or []
    if not isinstance(crosswalk, list):
        crosswalk = []
    row_labels = crosswalk_material_row_labels(crosswalk)
    gaps = list(payload.get("claim_gaps") or [])
    gap_text = " ".join(str(gap or "") for gap in gaps).lower()

    for label in inventory:
        key = label.lower()
        if key in row_labels:
            continue
        if key in gap_text:
            continue
        gaps.append(_GAP_TEMPLATE.format(label=label))
        gap_text = f"{gap_text} {key}"

    payload["claim_gaps"] = gaps
    return payload


def repair_eval_handoff(run_dir: Path) -> bool:
    """Deterministic eval pre-gate: manifest gap sync + evidence acronym expansion."""
    handoff_path = Path(run_dir) / "artifacts" / "eval_handoff.json"
    if not handoff_path.is_file():
        return False
    try:
        payload = load_handoff_dict(handoff_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.debug("eval repair skipped unreadable handoff: %s", exc)
        return False
    if not isinstance(payload, dict):
        return False

    scratchpad = Path(run_dir) / "artifacts" / "research_scratchpad.md"
    evidence_text = ""
    if scratchpad.is_file():
        try:
            evidence_text = scratchpad.read_text(encoding="utf-8", errors="replace")
        except OSError:
            evidence_text = ""

    before = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    repaired = sync_eval_claim_gaps_from_manifest(dict(payload), run_dir=run_dir)
    repaired = apply_known_acronym_expansions_to_eval_payload(
        repaired,
        evidence_text=evidence_text,
    )
    after = json.dumps(repaired, sort_keys=True, ensure_ascii=False)
    if after == before:
        return False

    handoff_path.write_text(
        json.dumps(repaired, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True