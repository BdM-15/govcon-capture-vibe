"""
Workspace processing-log tailer for the Documents tab "Workspace Activity Log".

Reads from the per-workspace log file produced by
:func:`src.utils.logging_config.setup_logging` (``{workspace_dir}/{workspace}_processing.log``)
and exposes:

* :func:`read_snapshot` — return the most recent N events (parsed log lines).
* :func:`stream_events` — async generator that yields newly-appended events as
  they're written. Polls the file every ~1.5s.

Each event has the shape::

    {
        "id": <int>,                    # monotonic per stream
        "ts": "2026-04-23 09:44:31",    # raw timestamp string from the log
        "ts_iso": "2026-04-23T09:44:31",# ISO-ish for the UI
        "level": "INFO" | "WARNING" | "ERROR" | "DEBUG",
        "logger": "src.server.routes",
        "message": "✅ Document completed: doc-… (28.2s, queue: 0 remaining)",
        "category": "processing" | "query" | "other",
        "kind": "info" | "success" | "error" | "warning" | "phase" | "queue" | "batch",
        "phase": {"index": 1, "label": "Data Loading"} | None,
    }

Why a tailer instead of an in-memory handler:
the per-workspace log file *is* the long-lived audit trail — it survives
restarts and is workspace-scoped by design. Reading it directly means the
Documents panel shows the full history every time the user opens the tab.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator, Optional

from src.server.workspace_log_parser import parse_workspace_log_lines

logger = logging.getLogger(__name__)

# Tail buffer cap for snapshots. ~500 lines comfortably covers a multi-doc
# upload batch + a chat session's worth of query traffic.
_DEFAULT_SNAPSHOT_LIMIT = 500
_HARD_SNAPSHOT_CAP = 2000

# Live-tail polling interval. 1.5s feels real-time enough for a log panel
# without spinning the CPU or filesystem unnecessarily.
_POLL_INTERVAL = 1.5

# How often to emit an SSE heartbeat comment when the file is idle, to keep
# proxies/browsers from closing the connection.
_HEARTBEAT_INTERVAL = 15.0




# ---------------------------------------------------------------------------
# File path resolution
# ---------------------------------------------------------------------------


def _log_path() -> Optional[Path]:
    """Return the active workspace's processing-log file path.

    Mirrors the layout used by :func:`src.utils.logging_config.setup_logging`:
    ``<working_dir>/<workspace>/<workspace>_processing.log``.
    """
    try:
        from lightrag.api.config import global_args  # type: ignore

        from src.core import get_settings  # local import: avoid cycles
    except Exception:  # noqa: BLE001
        return None
    try:
        ws = get_settings().workspace
        if not ws:
            return None
        return Path(global_args.working_dir) / ws / f"{ws}_processing.log"
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Snapshot (last-N lines)
# ---------------------------------------------------------------------------


def _read_tail_lines(path: Path, max_lines: int) -> list[str]:
    """Return the last ``max_lines`` lines of ``path`` (read efficiently).

    Uses a backwards block-read so we don't pull a multi-MB log into memory
    just to render the most recent ~500 entries.
    """
    block_size = 64 * 1024
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            data = bytearray()
            offset = file_size
            # Each "line" we want is timestamped; multi-line messages may share
            # a stamp, so over-read by 4× and trim at the end.
            target = max_lines * 4
            while offset > 0 and data.count(b"\n") < target:
                read_size = min(block_size, offset)
                offset -= read_size
                f.seek(offset)
                data[:0] = f.read(read_size)
            text = data.decode("utf-8", errors="replace")
    except FileNotFoundError:
        return []
    except OSError:
        return []
    lines = text.splitlines()
    # Drop a partial line at the start if we sliced mid-record.
    if offset > 0 and lines:
        lines = lines[1:]
    return lines


def read_snapshot(limit: int = _DEFAULT_SNAPSHOT_LIMIT) -> dict:
    """Read the most recent events from the active workspace's log file.

    Returns ``{"path": <str|None>, "events": [...], "exists": bool}``.
    Safe to call when no log file exists yet (returns an empty event list).
    """
    clamped = max(1, min(_HARD_SNAPSHOT_CAP, int(limit)))
    path = _log_path()
    if path is None:
        return {"path": None, "exists": False, "events": []}
    if not path.exists():
        return {"path": str(path), "exists": False, "events": []}
    raw = _read_tail_lines(path, clamped)
    events = parse_workspace_log_lines(raw)
    if len(events) > clamped:
        events = events[-clamped:]
        # Renumber ids so the client sees a contiguous monotonic sequence
        for i, ev in enumerate(events, start=1):
            ev["id"] = i
    return {"path": str(path), "exists": True, "events": events}


# ---------------------------------------------------------------------------
# Live tail (SSE-friendly async generator)
# ---------------------------------------------------------------------------


async def stream_events(
    initial_limit: int = 200,
    poll_interval: float = _POLL_INTERVAL,
    heartbeat_interval: float = _HEARTBEAT_INTERVAL,
) -> AsyncIterator[dict]:
    """Yield log events as they're appended to the active workspace's log file.

    Yields:
        Each yielded value is one of:

        * ``{"type": "snapshot", "events": [...], "path": str|None}`` — the
          first message, containing up to ``initial_limit`` recent events.
        * ``{"type": "event", "event": {...}}`` — a freshly-appended event.
        * ``{"type": "ping"}`` — heartbeat (caller decides whether to forward).

    Cancellation:
        The caller (FastAPI's StreamingResponse) is responsible for
        propagating client disconnect by cancelling the awaiting task; this
        generator simply exits cleanly when its loop is interrupted.
    """
    snapshot = read_snapshot(initial_limit)
    yield {
        "type": "snapshot",
        "events": snapshot["events"],
        "path": snapshot["path"],
    }

    next_id = (snapshot["events"][-1]["id"] + 1) if snapshot["events"] else 1
    path = _log_path()
    offset = 0
    if path and path.exists():
        try:
            offset = path.stat().st_size
        except OSError:
            offset = 0
    last_heartbeat = 0.0
    pending_partial = ""  # carry a half-written final line across polls

    loop = asyncio.get_running_loop()
    while True:
        try:
            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            return

        # Re-resolve path each iteration so a workspace switch (after a
        # restart) or log rotation transparently reattaches.
        current_path = _log_path()
        if current_path != path:
            path = current_path
            offset = 0
            pending_partial = ""

        if path is None or not path.exists():
            now = loop.time()
            if now - last_heartbeat >= heartbeat_interval:
                last_heartbeat = now
                yield {"type": "ping"}
            continue

        try:
            size = path.stat().st_size
        except OSError:
            continue

        if size < offset:
            # File was rotated/truncated. Reset and re-stream from scratch.
            offset = 0
            pending_partial = ""

        if size > offset:
            try:
                with path.open("rb") as f:
                    f.seek(offset)
                    chunk = f.read(size - offset)
                offset = size
            except OSError:
                continue
            text = pending_partial + chunk.decode("utf-8", errors="replace")
            # Hold back a trailing partial line until the next poll.
            if not text.endswith("\n"):
                last_nl = text.rfind("\n")
                if last_nl == -1:
                    pending_partial = text
                    text = ""
                else:
                    pending_partial = text[last_nl + 1 :]
                    text = text[: last_nl + 1]
            else:
                pending_partial = ""
            new_events = parse_workspace_log_lines(text.splitlines(), start_id=next_id)
            for ev in new_events:
                yield {"type": "event", "event": ev}
            next_id += len(new_events)
            last_heartbeat = loop.time()
            continue

        now = loop.time()
        if now - last_heartbeat >= heartbeat_interval:
            last_heartbeat = now
            yield {"type": "ping"}
