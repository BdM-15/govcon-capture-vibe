"""Model Context Protocol (MCP) client subsystem for the skill runtime.

Skills can declare ``metadata.mcps: [usaspending, sam_gov]`` in their
SKILL.md frontmatter to gain access to vendored MCP servers under
``tools/mcps/<name>/``. The runtime spawns one subprocess per declared
MCP per skill run, performs the JSON-RPC handshake, lists the server's
tools, and registers each as a ``ToolSpec`` named
``mcp__<server>__<tool>``. From the model's perspective, MCP tools look
identical to the in-process tools (``read_file``, ``kg_query``, etc.) —
they all flow through the same transcript, the same dispatch loop, and
the same error envelopes.

Design constraints (see ``docs/archive/phase_3-4/PHASE_4A_MCP_CLIENT_DESIGN.md``):

* **Transport:** stdio with **newline-delimited JSON** (per the official
  MCP spec — one JSON-RPC message per line, no embedded newlines).
* **Lifecycle:** one subprocess per MCP per skill run (no cross-run
  pooling). Spawned at the start of ``invoke``, reaped in the ``finally``
  of ``run_tool_loop`` via :meth:`MCPRegistry.shutdown_run`.
* **Allowlist:** the registry only spawns servers whose names appear in
  the calling skill's ``metadata.mcps``. Default is closed (empty list →
  zero MCP tools).
* **Manifest:** each vendored MCP carries
  ``tools/mcps/<name>/theseus_manifest.json`` describing the spawn
  command, required env vars, and upstream attribution. The manifest is
  Theseus-side glue and stays separate from upstream ``package.json`` /
  ``mcp.json`` so re-vendoring is a clean copy.

This module owns no global state; the route layer / SkillManager
constructs a single :class:`MCPRegistry` at startup and passes it into
each ``invoke``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.skills.mcp_session import MCPError, MCPManifest, MCPSession, discover_manifests, load_manifest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

@dataclass
class MCPStartupResult:
    """Outcome of starting all MCP sessions requested by one skill run."""

    sessions: dict[str, "MCPSession"] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def started_names(self) -> list[str]:
        return sorted(self.sessions)

    def warning_messages(self) -> list[str]:
        messages: list[str] = []
        if self.missing:
            messages.append(f"MCP servers requested but not installed: {self.missing}")
        if self.failed:
            messages.append(f"MCP servers failed to start: {self.failed}")
        return messages

# ---------------------------------------------------------------------------
# Registry — maps run_id → set of live sessions
# ---------------------------------------------------------------------------


class MCPRegistry:
    """Process-wide MCP session manager.

    The route layer / SkillManager constructs **one** registry at startup
    via :func:`MCPRegistry.from_root`. For each skill ``invoke``:

    1. Caller asks :meth:`start_run_sessions` for the MCPs the skill
       declared in its frontmatter.
    2. Caller passes ``MCPStartupResult.sessions`` into the runtime via
       :class:`ToolContext`, and can surface ``missing`` / ``failed`` as
       user-facing warnings.
    3. Caller (the runtime, via its ``finally`` block) calls
       :meth:`shutdown_run` to reap subprocesses.
    """

    def __init__(self, manifests: dict[str, MCPManifest]):
        self._manifests = dict(manifests)
        # run_id → list of sessions to reap
        self._run_sessions: dict[str, list[MCPSession]] = {}

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_root(cls, mcps_root: Path) -> "MCPRegistry":
        manifests = discover_manifests(mcps_root)
        if manifests:
            logger.info(
                "MCP registry loaded %d manifest(s): %s",
                len(manifests),
                ", ".join(sorted(manifests)),
            )
        else:
            logger.info("MCP registry: no manifests found at %s", mcps_root)
        return cls(manifests)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def known_mcps(self) -> list[str]:
        return sorted(self._manifests)

    def get_manifest(self, name: str) -> Optional[MCPManifest]:
        return self._manifests.get(name)

    # ------------------------------------------------------------------
    # Per-run lifecycle
    # ------------------------------------------------------------------

    async def start_run_sessions(
        self,
        run_id: str,
        requested: list[str],
        env_extra: Optional[dict[str, str]] = None,
    ) -> MCPStartupResult:
        """Spawn one session per requested MCP for this run.

        Unknown / failed MCPs are logged and recorded in the result; partial
        failures do not abort the run.
        """
        result = MCPStartupResult()
        if not requested:
            return result
        bucket = self._run_sessions.setdefault(run_id, [])
        for name in requested:
            manifest = self._manifests.get(name)
            if manifest is None:
                logger.warning(
                    "Skill requested MCP %r but no manifest is installed", name
                )
                result.missing.append(name)
                continue
            session = MCPSession(manifest)
            try:
                await session.start(env_extra=env_extra)
            except MCPError as exc:
                logger.warning("MCP %s failed to start: %s", name, exc)
                # session.start already shut itself down on failure.
                result.failed[name] = str(exc)
                continue
            result.sessions[name] = session
            bucket.append(session)
        return result

    async def shutdown_run(self, run_id: str) -> None:
        """Reap all sessions associated with ``run_id``. Idempotent."""
        bucket = self._run_sessions.pop(run_id, None)
        if not bucket:
            return
        await asyncio.gather(
            *(s.shutdown() for s in bucket), return_exceptions=True
        )

    async def shutdown_all(self) -> None:
        """Reap every live session. For server-shutdown hooks / tests."""
        for run_id in list(self._run_sessions):
            await self.shutdown_run(run_id)
