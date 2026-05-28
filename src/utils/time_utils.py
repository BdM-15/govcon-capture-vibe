"""
Time helpers — all user-visible timestamps in this app are emitted in
Central time (America/Chicago, which auto-handles CST/CDT).

Use these helpers anywhere a timestamp is written into doc_status, processing
logs, UI events, or filenames the user reads. Duration measurements should
keep using `time.time()` since they're tz-agnostic.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover — zoneinfo always present on 3.9+
    LOCAL_TZ = timezone.utc  # fallback so the app never crashes on a bad env


# Legacy ingestion once emitted local timestamps mislabeled as UTC (no
# microseconds, literal "+00:00" suffix). Detect that exact shape and treat it
# as naive-local.
_LOCAL_PLUS_ZERO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$"
)


def now_local() -> datetime:
    """Current time as a tz-aware datetime in America/Chicago."""
    return datetime.now(LOCAL_TZ)


def now_local_iso(timespec: str = "seconds") -> str:
    """ISO 8601 string in America/Chicago, e.g. '2026-04-27T07:39:10-05:00'."""
    return now_local().isoformat(timespec=timespec)


def to_local_iso(value: object, timespec: str = "seconds") -> Optional[str]:
    """
    Convert an arbitrary timestamp to an America/Chicago ISO string.

    Accepts: tz-aware datetime, naive datetime (assumed UTC, since LightRAG
    writes UTC internally), ISO 8601 string, or epoch int/float. Returns the
    original value on parse failure (callers may pass through unknown junk).
    """
    if value is None or value == "":
        return value  # type: ignore[return-value]
    try:
        if isinstance(value, datetime):
            dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        elif isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        elif isinstance(value, str):
            s = value.strip()
            # Legacy value is actually local time mislabeled as UTC.
            # Reinterpret as naive local instead of converting from UTC.
            if _LOCAL_PLUS_ZERO_RE.match(s):
                naive = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
                dt = naive.replace(tzinfo=LOCAL_TZ)
            else:
                # Python's fromisoformat handles 'Z' only on 3.11+; normalize.
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
        else:
            return value  # type: ignore[return-value]
        return dt.astimezone(LOCAL_TZ).isoformat(timespec=timespec)
    except Exception:
        return value  # type: ignore[return-value]
