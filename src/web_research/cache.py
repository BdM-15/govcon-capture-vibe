"""Simple JSON file cache for web research responses."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _key_digest(namespace: str, value: str) -> str:
    payload = f"{namespace}:{value}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def cache_get(cache_dir: Path, namespace: str, key: str, *, ttl_seconds: int) -> dict[str, Any] | None:
    if ttl_seconds <= 0 or not cache_dir.exists():
        return None
    path = cache_dir / f"{_key_digest(namespace, key)}.json"
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    saved_at = float(record.get("saved_at") or 0)
    if saved_at <= 0 or (time.time() - saved_at) > ttl_seconds:
        return None
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else None


def cache_set(cache_dir: Path, namespace: str, key: str, payload: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{_key_digest(namespace, key)}.json"
    record = {"saved_at": time.time(), "payload": payload}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)