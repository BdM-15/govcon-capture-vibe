"""Structured chain execution events for live UI timeline (Tier 1 observability)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ChainEvent:
    chain_id: str
    phase: str
    event: str
    summary: str
    step_id: str = ""
    skill: str = ""
    status: str = ""
    elapsed_ms: int = 0
    ts: str = field(default_factory=_utc_now_iso)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def chain_events_path(chain_dir: Path) -> Path:
    return Path(chain_dir) / "events.jsonl"


def emit_chain_event(chain_dir: Path, event: ChainEvent) -> None:
    path = chain_events_path(chain_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


def read_chain_events(chain_dir: Path, *, tail: int = 200) -> list[dict[str, Any]]:
    path = chain_events_path(chain_dir)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    events: list[dict[str, Any]] = []
    for line in lines[-tail:]:
        line = line.strip()
        if not line:
            continue
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            events.append(loaded)
    return events