"""Document activity log routes and parsing helpers for Theseus UI."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Callable, Iterable
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

ReadSnapshot = Callable[..., dict[str, Any]]
StreamEvents = Callable[..., AsyncIterator[dict[str, Any]]]

# Format produced by logging_config.detailed_formatter:
#   %(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s
# datefmt = %Y-%m-%d %H:%M:%S
_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\|\s*"
    r"(?P<level>\w+)\s*\|\s*"
    r"(?P<logger>[\w\.\-]+)\s*\|\s?"
    r"(?P<msg>.*)$"
)

# Phase headers from src.inference.semantic_post_processor and lightrag.operate.
_PHASE_RE = re.compile(r"Phase\s+(\d+)\s*[·:.\-]?\s*([A-Za-z][A-Za-z &/\-]*)?")

_PROCESSING_LOGGERS = (
    "src.server.routes",
    "src.server.initialization",
    "src.inference",
    "src.extraction",
    "src.ontology",
    "src.server.processing_log",
    "raganything",
    "nano-vectordb",
)

_QUERY_LOGGERS = ("src.server.ui_routes",)

_LIGHTRAG_PROCESSING_MARKERS = (
    "Parsing",
    "Phase ",
    "Chunk ",
    "chunk-",
    "extracted",
    "Extracting stage",
    "Merging",
    "Merged:",
    "Multimodal",
    "Content Information",
    "Content separation",
    "Content source",
    "Content list insertion",
    "Processing d-id",
    "Processing 1 document",
    "In memory DB persist",
    "Completed merging",
    "Completed processing",
    "Text content insertion",
    "MinerU",
    "Stored parsing result",
    "LLM cache == saving",
    "LLM func:",
    "Detected Office",
    "Using mineru parser",
    "Starting document parsing",
    "Starting direct content list insertion",
    "Starting to process",
    "Starting multimodal",
    "Starting text content insertion",
    "chunk_tracking",
    "Generated descriptions",
    "Added ",
    "Enqueued document",
)

_LIGHTRAG_QUERY_MARKERS = (
    "kw_extract",
    "Local query",
    "Global query",
    "Naive query",
    "Hybrid query",
    "Mix query",
    "Re-ranking",
    "Reranking",
    "Rerank",
    "Retrieved ",
    "Query Retrieval",
    "Query mode",
    "Final context",
    "Final chunks",
    "Trim context",
    "context len",
    "Round ",
    "Initial entities",
    "Initial relations",
    "After truncation",
    "Truncate",
    "high_level_keywords",
    "low_level_keywords",
    "Query nodes",
    "Query edges",
    "Raw search results",
    "Selecting ",
    "additional chunks",
    "Round-robin merged",
    "reranked",
    "deduplicated",
)

_DEFAULT_SNAPSHOT_LIMIT = 500
_HARD_SNAPSHOT_CAP = 2000
_POLL_INTERVAL = 1.5
_HEARTBEAT_INTERVAL = 15.0


def classify_workspace_log_event(record_logger: str, message: str, level: str) -> dict[str, Any]:
    """Tag one parsed log line with category, kind, and optional phase."""
    name = record_logger or ""
    msg = message or ""
    upper = level.upper() if level else ""

    if any(name == item or name.startswith(item + ".") for item in _PROCESSING_LOGGERS):
        category = "processing"
    elif any(name == item or name.startswith(item + ".") for item in _QUERY_LOGGERS):
        category = "query"
    elif name == "lightrag" or name.startswith("lightrag."):
        if any(marker in msg for marker in _LIGHTRAG_PROCESSING_MARKERS) or upper in {"WARNING", "ERROR", "CRITICAL"}:
            category = "processing"
        elif any(marker in msg for marker in _LIGHTRAG_QUERY_MARKERS):
            category = "query"
        else:
            category = "other"
    else:
        category = "other"

    if upper in {"ERROR", "CRITICAL"}:
        kind = "error"
    elif upper == "WARNING":
        kind = "warning"
    elif "❌" in msg:
        kind = "error"
    elif "✅" in msg or "complete" in msg.lower():
        kind = "success"
    elif "⚙️" in msg or "🚀" in msg or "Phase " in msg:
        kind = "phase"
    elif "📥" in msg or "🏁" in msg:
        kind = "queue"
    elif "🎯" in msg:
        kind = "batch"
    else:
        kind = "info"

    phase = None
    match = _PHASE_RE.search(msg)
    if match:
        phase = {"index": int(match.group(1)), "label": (match.group(2) or "").strip() or None}

    return {"category": category, "kind": kind, "phase": phase}


def parse_workspace_log_lines(lines: Iterable[str], start_id: int = 1) -> list[dict[str, Any]]:
    """Parse raw log lines into UI events, folding continuation lines."""
    events: list[dict[str, Any]] = []
    next_id = start_id
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line:
            if events:
                events[-1]["message"] += "\n"
            continue
        match = _LINE_RE.match(line)
        if not match:
            if events:
                events[-1]["message"] += "\n" + line
            continue
        ts = match.group("ts")
        level = match.group("level").strip()
        log_name = match.group("logger").strip()
        msg = match.group("msg")
        events.append(
            {
                "id": next_id,
                "ts": ts,
                "ts_iso": ts.replace(" ", "T"),
                "level": level,
                "logger": log_name,
                "message": msg,
                **classify_workspace_log_event(log_name, msg, level),
            }
        )
        next_id += 1
    return events


def _log_path() -> Optional[Path]:
    """Return active workspace processing-log file path."""
    try:
        from lightrag.api.config import global_args  # type: ignore
        from src.core import get_settings
    except Exception:  # noqa: BLE001
        return None
    try:
        workspace = get_settings().workspace
        if not workspace:
            return None
        return Path(global_args.working_dir) / workspace / f"{workspace}_processing.log"
    except Exception:  # noqa: BLE001
        return None


def _read_tail_lines(path: Path, max_lines: int) -> list[str]:
    """Return last ``max_lines`` lines of ``path`` using backwards block-read."""
    block_size = 64 * 1024
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            file_size = handle.tell()
            data = bytearray()
            offset = file_size
            target = max_lines * 4
            while offset > 0 and data.count(b"\n") < target:
                read_size = min(block_size, offset)
                offset -= read_size
                handle.seek(offset)
                data[:0] = handle.read(read_size)
            text = data.decode("utf-8", errors="replace")
    except FileNotFoundError:
        return []
    except OSError:
        return []
    lines = text.splitlines()
    if offset > 0 and lines:
        lines = lines[1:]
    return lines


def read_snapshot(limit: int = _DEFAULT_SNAPSHOT_LIMIT) -> dict[str, Any]:
    """Read most recent events from active workspace log file."""
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
        for index, event in enumerate(events, start=1):
            event["id"] = index
    return {"path": str(path), "exists": True, "events": events}


async def stream_events(
    initial_limit: int = 200,
    poll_interval: float = _POLL_INTERVAL,
    heartbeat_interval: float = _HEARTBEAT_INTERVAL,
) -> AsyncIterator[dict[str, Any]]:
    """Yield log events as they are appended to active workspace log file."""
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
    pending_partial = ""

    loop = asyncio.get_running_loop()
    while True:
        try:
            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            return

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
            offset = 0
            pending_partial = ""

        if size > offset:
            try:
                with path.open("rb") as handle:
                    handle.seek(offset)
                    chunk = handle.read(size - offset)
                offset = size
            except OSError:
                continue
            text = pending_partial + chunk.decode("utf-8", errors="replace")
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
            for event in new_events:
                yield {"type": "event", "event": event}
            next_id += len(new_events)
            last_heartbeat = loop.time()
            continue

        now = loop.time()
        if now - last_heartbeat >= heartbeat_interval:
            last_heartbeat = now
            yield {"type": "ping"}


def register_processing_log_routes(
    app: FastAPI,
    *,
    read_log_snapshot: ReadSnapshot = read_snapshot,
    stream_log_events: StreamEvents = stream_events,
) -> None:
    """Register processing-log snapshot and SSE routes."""

    @app.get("/api/ui/processing-log", tags=["theseus-ui"])
    async def ui_processing_log_snapshot(limit: int = 500) -> JSONResponse:
        """Return most recent events from workspace activity log."""
        return JSONResponse(read_log_snapshot(limit=limit))

    @app.get("/api/ui/processing-log/stream", tags=["theseus-ui"])
    async def ui_processing_log_stream(limit: int = 200) -> StreamingResponse:
        """Stream new workspace-log events to Documents tab via SSE."""

        async def event_stream() -> AsyncIterator[str]:
            try:
                yield "event: open\ndata: {}\n\n"
                async for item in stream_log_events(initial_limit=limit):
                    if item["type"] == "snapshot":
                        yield (
                            "event: snapshot\ndata: "
                            + json.dumps(
                                {"events": item["events"], "path": item.get("path")}
                            )
                            + "\n\n"
                        )
                    elif item["type"] == "event":
                        yield (
                            "event: event\ndata: "
                            + json.dumps(item["event"])
                            + "\n\n"
                        )
                    else:
                        yield ": ping\n\n"
            except asyncio.CancelledError:
                raise

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )


__all__ = [
    "classify_workspace_log_event",
    "parse_workspace_log_lines",
    "read_snapshot",
    "register_processing_log_routes",
    "stream_events",
]