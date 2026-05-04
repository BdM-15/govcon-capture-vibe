"""Logging filter helpers for console, processing, and server logs."""

from __future__ import annotations

import logging


class ConsoleFilter(logging.Filter):
    """Allowlist filter for console output."""

    _ALLOWED = {
        "src.raganything_server",
        "uvicorn.error",
        "src.server.routes",
        "src.inference",
        "src.extraction.govcon_reranker",
    }

    def filter(self, record):
        if record.levelno >= logging.WARNING:
            return True
        if record.name == "uvicorn.access":
            return False
        return any(
            record.name == name or record.name.startswith(name + ".")
            for name in self._ALLOWED
        )


class ProcessingFilter(logging.Filter):
    """Capture RFP processing logs for per-workspace processing logs."""

    _PROCESSING_LOGGERS = [
        "lightrag",
        "raganything",
        "src.server.routes",
        "src.inference",
        "src.ingestion",
        "src.extraction.govcon_reranker",
    ]
    _PROCESSING_KEYWORDS = [
        "Processing",
        "entities",
        "relationships",
        "semantic",
        "GraphML",
        "Neo4j",
        "inference",
        "enrichment",
        "parsing",
        "extraction",
    ]

    def filter(self, record):
        for logger_name in self._PROCESSING_LOGGERS:
            if record.name.startswith(logger_name):
                return True
        message = record.getMessage()
        return any(keyword in message for keyword in self._PROCESSING_KEYWORDS)


class ServerFilter(logging.Filter):
    """Exclude deep processing logs from central server log."""

    _PROCESSING_LOGGERS = [
        "lightrag.llm",
        "lightrag.kg",
        "raganything",
    ]

    def filter(self, record):
        for logger_name in self._PROCESSING_LOGGERS:
            if record.name.startswith(logger_name):
                return False
        return True