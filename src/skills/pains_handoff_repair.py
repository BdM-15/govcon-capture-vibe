"""Platform repair for readiness-frame-pains handoff shape mistakes."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.readiness_handoff_models import load_handoff_dict, normalize_pains_payload


def repair_pains_handoff(run_dir: Path) -> bool:
    """Normalize pains_handoff.json rows (visibility/challenge_type swap) before gate."""
    path = Path(run_dir) / "artifacts" / "pains_handoff.json"
    if not path.is_file():
        return False
    try:
        payload = load_handoff_dict(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    repaired = normalize_pains_payload(payload)
    before = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    after = json.dumps(repaired, sort_keys=True, ensure_ascii=False)
    if after == before:
        return False
    path.write_text(json.dumps(repaired, ensure_ascii=False, indent=2), encoding="utf-8")
    return True