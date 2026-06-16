"""Platform repair for readiness-frame-tea-leaves handoff shape mistakes."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.readiness_handoff_models import (
    load_handoff_dict,
    normalize_tea_leaves_payload,
)


def repair_tea_leaves_handoff(run_dir: Path) -> bool:
    """Normalize tea_leaves_handoff.json rows and extract embedded chunk IDs."""
    path = Path(run_dir) / "artifacts" / "tea_leaves_handoff.json"
    if not path.is_file():
        return False
    try:
        payload = load_handoff_dict(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    repaired = normalize_tea_leaves_payload(payload)
    before = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    after = json.dumps(repaired, sort_keys=True, ensure_ascii=False)
    if after == before:
        return False
    path.write_text(json.dumps(repaired, ensure_ascii=False, indent=2), encoding="utf-8")
    return True