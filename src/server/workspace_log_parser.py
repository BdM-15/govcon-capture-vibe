"""Parsing and classification helpers for workspace processing logs."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

# Format produced by logging_config.detailed_formatter:
#   %(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s
# datefmt = %Y-%m-%d %H:%M:%S
_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\|\s*"
    r"(?P<level>\w+)\s*\|\s*"
    r"(?P<logger>[\w\.\-]+)\s*\|\s?"
    r"(?P<msg>.*)$"
)

# Phase headers from src.inference.semantic_post_processor and lightrag.operate:
#   "Phase 1 · Data Loading", "Phase 1: Processing 61 entities…"
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