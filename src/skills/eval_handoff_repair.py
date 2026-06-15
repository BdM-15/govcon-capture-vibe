"""Deterministic pre-gate repair for readiness-frame-eval handoffs."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.skills.readiness_content_gates import apply_known_acronym_expansions_to_eval_payload
from src.skills.readiness_handoff_models import load_handoff_dict

logger = logging.getLogger(__name__)


def repair_eval_handoff(run_dir: Path) -> bool:
    """Expand dict-known acronyms in eval_handoff.json before gate (no LLM)."""
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
    repaired = apply_known_acronym_expansions_to_eval_payload(
        dict(payload),
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