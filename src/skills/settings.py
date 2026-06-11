"""Runtime settings helpers for the skills subsystem."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from src.core.env import env_float, env_int

logger = logging.getLogger(__name__)

VALID_SKILL_RUNTIME_MODES = {"tools", "legacy"}
VALID_SKILL_RETRIEVAL_MODES = {"hybrid", "local", "global", "naive", "mix", "off"}


DEFAULT_SKILL_MAX_PAYLOAD_CHARS = env_int("SKILL_MAX_PAYLOAD_CHARS", 200_000)
SKILL_TOOLS_RUNTIME_ENV_DEFAULTS = {
    "max_turns": 25,
    "llm_timeout_seconds": 180.0,
    "mcp_handshake_timeout": 15.0,
    "mcp_tool_call_timeout": 60.0,
    "mcp_shutdown_timeout": 3.0,
    "max_tool_result_chars": 50_000,
    "max_read_bytes": 200_000,
    "max_write_bytes": 1_000_000,
    "max_script_seconds": 120,
    "max_kg_entities_per_type": 100,
    "max_kg_chunks": 100,
    "max_kg_chunks_per_entity": 15,
    "max_kg_relationships_per_entity": 25,
}
SKILL_TOOLS_RUNTIME_ENV_KEYS = {
    "max_turns": "SKILL_TOOLS_MAX_TURNS",
    "llm_timeout_seconds": "SKILL_TOOLS_LLM_TIMEOUT",
    "mcp_handshake_timeout": "MCP_HANDSHAKE_TIMEOUT",
    "mcp_tool_call_timeout": "MCP_TOOL_CALL_TIMEOUT",
    "mcp_shutdown_timeout": "MCP_SHUTDOWN_TIMEOUT",
    "max_tool_result_chars": "SKILL_TOOLS_MAX_TOOL_RESULT_CHARS",
    "max_read_bytes": "SKILL_TOOLS_MAX_READ_BYTES",
    "max_write_bytes": "SKILL_TOOLS_MAX_WRITE_BYTES",
    "max_script_seconds": "SKILL_TOOLS_MAX_SCRIPT_SECONDS",
    "max_kg_entities_per_type": "SKILL_TOOLS_MAX_KG_ENTITIES_PER_TYPE",
    "max_kg_chunks": "SKILL_TOOLS_MAX_KG_CHUNKS",
    "max_kg_chunks_per_entity": "SKILL_TOOLS_MAX_CHUNKS_PER_ENTITY",
    "max_kg_relationships_per_entity": "SKILL_TOOLS_MAX_RELATIONSHIPS_PER_ENTITY",
}


@dataclass(frozen=True)
class SkillToolsRuntimeLimits:
    """Process-wide hard caps for tools-mode skill runs."""

    llm_timeout_seconds: float
    max_tool_result_chars: int
    max_read_bytes: int
    max_write_bytes: int
    max_script_seconds: int
    max_kg_entities_per_type: int
    max_kg_chunks: int
    max_kg_chunks_per_entity: int
    max_kg_relationships_per_entity: int


def resolve_skill_runtime_mode(
    frontmatter_mode: str,
    *,
    runtime_mode_override: Optional[str] = None,
) -> str:
    """Resolve skill runtime mode using override, env, then frontmatter."""
    env_override = os.getenv("SKILL_RUNTIME_MODE", "").strip().lower()
    requested = (runtime_mode_override or "").strip().lower()
    if requested in VALID_SKILL_RUNTIME_MODES:
        return requested
    if env_override in VALID_SKILL_RUNTIME_MODES:
        return env_override
    normalized = (frontmatter_mode or "").strip().lower()
    return "tools" if normalized == "tools" else "legacy"


def skill_tools_max_turns(metadata: Mapping[str, Any]) -> int:
    """Return the effective tools-mode turn budget for one skill."""
    env_max_turns = env_int("SKILL_TOOLS_MAX_TURNS", 25)
    raw = metadata.get("max_turns")
    if isinstance(raw, int) and raw > env_max_turns:
        return raw
    return env_max_turns


def skill_tools_runtime_limits() -> SkillToolsRuntimeLimits:
    """Return the effective tools-mode hard caps from `.env`."""
    return SkillToolsRuntimeLimits(
        llm_timeout_seconds=env_float("SKILL_TOOLS_LLM_TIMEOUT", 180.0, 1.0, 3600.0),
        max_tool_result_chars=env_int(
            "SKILL_TOOLS_MAX_TOOL_RESULT_CHARS", 50_000, 500, 2_000_000
        ),
        max_read_bytes=env_int("SKILL_TOOLS_MAX_READ_BYTES", 200_000, 1_000, 5_000_000),
        max_write_bytes=env_int(
            "SKILL_TOOLS_MAX_WRITE_BYTES", 1_000_000, 1_000, 20_000_000
        ),
        max_script_seconds=env_int("SKILL_TOOLS_MAX_SCRIPT_SECONDS", 120, 1, 86_400),
        max_kg_entities_per_type=env_int(
            "SKILL_TOOLS_MAX_KG_ENTITIES_PER_TYPE", 100, 1, 5_000
        ),
        max_kg_chunks=env_int("SKILL_TOOLS_MAX_KG_CHUNKS", 100, 1, 5_000),
        max_kg_chunks_per_entity=env_int(
            "SKILL_TOOLS_MAX_CHUNKS_PER_ENTITY", 15, 0, 500
        ),
        max_kg_relationships_per_entity=env_int(
            "SKILL_TOOLS_MAX_RELATIONSHIPS_PER_ENTITY", 25, 0, 500
        ),
    )


def skill_tools_runtime_settings() -> dict[str, int | float]:
    """Return tools-mode runtime limits as a plain dict for the UI/API."""
    limits = skill_tools_runtime_limits()
    data = asdict(limits)
    data["max_turns"] = skill_tools_max_turns({})
    return data


def skill_tools_runtime_defaults() -> dict[str, int | float]:
    """Return recommended default values for tools-mode runtime caps."""
    return dict(SKILL_TOOLS_RUNTIME_ENV_DEFAULTS)


def mcp_handshake_timeout() -> float:
    """Timeout in seconds for MCP handshake and tool listing."""
    return env_float("MCP_HANDSHAKE_TIMEOUT", 15.0, 0.1)


def mcp_tool_call_timeout() -> float:
    """Timeout in seconds for one MCP tool call."""
    return env_float("MCP_TOOL_CALL_TIMEOUT", 60.0, 0.1)


def mcp_shutdown_timeout() -> float:
    """Timeout in seconds for graceful MCP subprocess shutdown."""
    return env_float("MCP_SHUTDOWN_TIMEOUT", 3.0, 0.1)


def mcp_stdio_buffer_limit() -> int:
    """Maximum bytes asyncio will buffer for one MCP stdio line."""
    return env_int("MCP_STDIO_BUFFER_LIMIT", 16_000_000, 65_536, 100_000_000)


class SkillSettingsStore:
    """Per-workspace skill invocation settings backed by JSON files."""

    def __init__(self, workspace_dir: Callable[[], Path]) -> None:
        self._workspace_dir = workspace_dir

    @staticmethod
    def _env_skill_mode() -> str:
        raw = (os.getenv("SKILL_RETRIEVAL_MODE") or "mix").strip().lower()
        return raw if raw in VALID_SKILL_RETRIEVAL_MODES else "mix"

    def path(self) -> Path:
        return self._workspace_dir() / "ui_skill_settings.json"

    def defaults(self) -> dict[str, Any]:
        return {
            "max_entities_per_type": env_int(
                "SKILL_MAX_ENTITIES_PER_TYPE", 40, 1, 500
            ),
            "max_chunks_per_entity": env_int(
                "SKILL_MAX_CHUNKS_PER_ENTITY", 3, 0, 10
            ),
            "max_relationships_per_entity": env_int(
                "SKILL_MAX_RELATIONSHIPS_PER_ENTITY", 8, 0, 50
            ),
            "retrieval_mode": self._env_skill_mode(),
            "retrieval_top_k": env_int("SKILL_RETRIEVAL_TOP_K", 60, 5, 500),
        }

    def read(self) -> dict[str, Any]:
        merged = self.defaults()
        path = self.path()
        if not path.exists():
            return merged
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key in list(merged.keys()):
                    if key in loaded:
                        merged[key] = loaded[key]
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed reading %s, using defaults: %s", path, exc)
        return merged

    def write(self, data: dict[str, Any]) -> None:
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
