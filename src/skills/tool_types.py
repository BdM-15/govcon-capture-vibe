"""Shared runtime types for skill tool handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

SliceFn = Callable[
    [Optional[list[str]], int, int, int, Optional[set[str]]],
    dict[str, Any],
]

RetrieveFn = Callable[
    [str, str, str, int],
    Awaitable[dict[str, Any]],
]


@dataclass
class ToolContext:
    skill_name: str
    skill_dir: Path
    run_dir: Path
    workspace_dir: Path
    workspace_name: str
    slice_fn: Optional[SliceFn] = None
    retrieve_fn: Optional[RetrieveFn] = None
    max_read_bytes: int = 200_000
    max_write_bytes: int = 1_000_000
    max_script_seconds: int = 60
    max_kg_entities_per_type: int = 50
    max_kg_chunks: int = 30
    extra_script_roots: list[Path] = field(default_factory=list)
    mcp_sessions: dict[str, Any] = field(default_factory=dict)
    call_seq: list[int] = field(default_factory=lambda: [0])


@dataclass
class ToolResult:
    payload: Any
    truncated: bool = False
    transcript_extra: dict[str, Any] = field(default_factory=dict)


class ToolError(Exception):
    """Raised when a tool call fails (path violation, timeout, etc.)."""