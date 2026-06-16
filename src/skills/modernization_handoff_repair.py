"""Platform repair for readiness-frame-modernization handoff shape mistakes."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.readiness_handoff_models import (
    load_handoff_dict,
    normalize_modernization_payload,
)


def repair_modernization_handoff(run_dir: Path) -> bool:
    """Normalize modernization_handoff.json field aliases before gate."""
    path = Path(run_dir) / "artifacts" / "modernization_handoff.json"
    if not path.is_file():
        return False
    try:
        payload = load_handoff_dict(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    repaired = normalize_modernization_payload(payload)
    before = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    after = json.dumps(repaired, sort_keys=True, ensure_ascii=False)
    if after == before:
        return False
    path.write_text(json.dumps(repaired, ensure_ascii=False, indent=2), encoding="utf-8")
    return True