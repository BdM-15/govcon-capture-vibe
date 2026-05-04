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
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.skills.mcp_manifest import MCPManifest, discover_manifests, load_manifest
from src.skills.settings import (
    mcp_handshake_timeout,
    mcp_shutdown_timeout,
    mcp_tool_call_timeout,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# OpenAI tool-name limit. ``mcp__<server>__<tool>`` must fit.
_TOOL_NAME_MAX = 64

# JSON-RPC protocol version used in the initialize request. The MCP spec
# pins this to a date string; we stay current with the latest stable.
_MCP_PROTOCOL_VERSION = "2025-06-18"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MCPError(Exception):
    """Raised for any MCP-side failure (spawn, handshake, call, shutdown).

    The runtime catches this and surfaces it in the transcript the same way
    it surfaces ``ToolError``, so the model can recover gracefully.
    """


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
# Session — one subprocess + JSON-RPC plumbing
# ---------------------------------------------------------------------------


@dataclass
class MCPToolDescriptor:
    """An MCP-discovered tool, ready to be wrapped into a ToolSpec."""

    server: str  # MCP alias (manifest name)
    name: str  # upstream tool name
    description: str
    input_schema: dict[str, Any]

    @property
    def namespaced_name(self) -> str:
        """Tool name as exposed to the LLM. Capped to OpenAI's 64-char limit."""
        candidate = f"mcp__{self.server}__{self.name}"
        if len(candidate) > _TOOL_NAME_MAX:
            # Aggressive truncation last-resort; manifest validation should
            # normally catch this earlier so it stays predictable.
            candidate = candidate[:_TOOL_NAME_MAX]
        return candidate


class MCPSession:
    """One running MCP subprocess + JSON-RPC client.

    Not safe for concurrent ``call_tool`` from multiple coroutines on the
    same instance — the runtime's dispatch loop is sequential per turn,
    which matches this constraint.
    """

    def __init__(self, manifest: MCPManifest):
        self.manifest = manifest
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._stderr_task: Optional[asyncio.Task[None]] = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._tools: list[MCPToolDescriptor] = []
        self._closed = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, env_extra: Optional[dict[str, str]] = None) -> None:
        """Spawn the subprocess and complete the MCP handshake.

        Raises :class:`MCPError` on any failure (missing binary, missing
        required env, handshake timeout, malformed responses).
        """
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)
        missing = self.manifest.missing_env(env)
        if missing:
            raise MCPError(
                f"MCP {self.manifest.name!r} missing required env vars: {missing}"
            )

        # Resolve the executable on PATH so error messages are informative
        # (otherwise asyncio just raises FileNotFoundError with no hint).
        exe = self.manifest.command[0]
        resolved = shutil.which(exe) or exe
        argv = [resolved, *self.manifest.command[1:]]

        try:
            self._proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(self.manifest.cwd),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            raise MCPError(
                f"MCP {self.manifest.name!r}: executable not found ({exe}). "
                "Check theseus_manifest.json command[0] and PATH."
            ) from exc
        except OSError as exc:
            raise MCPError(f"MCP {self.manifest.name!r}: spawn failed: {exc}") from exc

        # Background readers: stdout demuxes JSON-RPC responses by id;
        # stderr drains so the OS pipe buffer never blocks the child.
        self._reader_task = asyncio.create_task(
            self._read_stdout_loop(),
            name=f"mcp-{self.manifest.name}-stdout",
        )
        self._stderr_task = asyncio.create_task(
            self._drain_stderr_loop(),
            name=f"mcp-{self.manifest.name}-stderr",
        )

        handshake_timeout = mcp_handshake_timeout()
        try:
            await asyncio.wait_for(self._handshake(), timeout=handshake_timeout)
            self._tools = await asyncio.wait_for(
                self._fetch_tools(), timeout=handshake_timeout
            )
        except asyncio.TimeoutError as exc:
            await self.shutdown()
            raise MCPError(
                f"MCP {self.manifest.name!r}: handshake/tool-list timed out "
                f"after {handshake_timeout}s"
            ) from exc
        except MCPError:
            await self.shutdown()
            raise
        logger.info(
            "MCP %s started: %d tools (%s)",
            self.manifest.name,
            len(self._tools),
            ", ".join(t.name for t in self._tools[:6]) + ("…" if len(self._tools) > 6 else ""),
        )

    async def shutdown(self) -> None:
        """Terminate the subprocess and cancel reader tasks. Idempotent."""
        if self._closed:
            return
        self._closed = True

        # Try a polite shutdown notification first; ignore failures.
        proc = self._proc
        if proc is not None and proc.returncode is None:
            try:
                await self._send({"jsonrpc": "2.0", "method": "shutdown"})
            except Exception:  # noqa: BLE001 — best-effort polite close
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=mcp_shutdown_timeout())
            except asyncio.TimeoutError:
                logger.info("MCP %s did not exit cleanly; terminating", self.manifest.name)
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except (ProcessLookupError, asyncio.TimeoutError):
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass

        for task in (self._reader_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

        # Fail any in-flight calls so callers don't hang.
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(
                    MCPError(f"MCP {self.manifest.name!r}: session closed")
                )
        self._pending.clear()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def tools(self) -> list[MCPToolDescriptor]:
        return list(self._tools)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Invoke one tool. Returns the concatenated text content.

        Raises :class:`MCPError` if the server reports ``isError: true`` or
        any transport failure occurs.
        """
        if self._closed:
            raise MCPError(f"MCP {self.manifest.name!r}: session is closed")
        timeout = mcp_tool_call_timeout()
        try:
            response = await asyncio.wait_for(
                self._request("tools/call", {"name": tool_name, "arguments": arguments}),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            raise MCPError(
                f"MCP {self.manifest.name!r}: tool {tool_name!r} timed out "
                f"after {timeout}s"
            ) from exc

        result = response.get("result") or {}
        is_error = bool(result.get("isError"))
        text = _extract_text_content(result.get("content"))
        if is_error:
            raise MCPError(
                f"MCP {self.manifest.name!r} tool {tool_name!r} returned an error: {text or '(no detail)'}"
            )
        return text

    # ------------------------------------------------------------------
    # JSON-RPC plumbing
    # ------------------------------------------------------------------

    async def _handshake(self) -> None:
        response = await self._request(
            "initialize",
            {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "theseus-skill-runtime", "version": "0.1"},
            },
        )
        if "error" in response:
            raise MCPError(
                f"MCP {self.manifest.name!r}: initialize error: {response['error']}"
            )
        # Tell the server we're ready for normal traffic. This is a
        # notification (no id), so we don't await a response.
        await self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    async def _fetch_tools(self) -> list[MCPToolDescriptor]:
        response = await self._request("tools/list", {})
        if "error" in response:
            raise MCPError(
                f"MCP {self.manifest.name!r}: tools/list error: {response['error']}"
            )
        result = response.get("result") or {}
        raw_tools = result.get("tools") or []
        descriptors: list[MCPToolDescriptor] = []
        for entry in raw_tools:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            schema = entry.get("inputSchema") or {"type": "object", "properties": {}}
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            descriptors.append(
                MCPToolDescriptor(
                    server=self.manifest.name,
                    name=name,
                    description=str(entry.get("description") or "").strip(),
                    input_schema=schema,
                )
            )
        return descriptors

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a request and await its keyed response."""
        if self._proc is None:
            raise MCPError(f"MCP {self.manifest.name!r}: not started")
        self._next_id += 1
        msg_id = self._next_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        try:
            await self._send(
                {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
            )
            return await future
        finally:
            self._pending.pop(msg_id, None)

    async def _send(self, message: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise MCPError(f"MCP {self.manifest.name!r}: stdin unavailable")
        line = json.dumps(message, ensure_ascii=False) + "\n"
        try:
            self._proc.stdin.write(line.encode("utf-8"))
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise MCPError(
                f"MCP {self.manifest.name!r}: write failed (subprocess gone): {exc}"
            ) from exc

    async def _read_stdout_loop(self) -> None:
        """Demux server → client JSON-RPC messages by id."""
        assert self._proc is not None and self._proc.stdout is not None
        stdout = self._proc.stdout
        try:
            while True:
                raw = await stdout.readline()
                if not raw:
                    break  # EOF — subprocess exited
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(
                        "MCP %s: malformed JSON on stdout: %r",
                        self.manifest.name,
                        line[:200],
                    )
                    continue
                if not isinstance(msg, dict):
                    continue
                msg_id = msg.get("id")
                if msg_id is None:
                    # Server-initiated notification — log and ignore
                    # (we don't subscribe to anything yet).
                    method = msg.get("method")
                    if method:
                        logger.debug(
                            "MCP %s server notification: %s",
                            self.manifest.name,
                            method,
                        )
                    continue
                fut = self._pending.get(int(msg_id))
                if fut is None:
                    logger.debug(
                        "MCP %s: response for unknown id %s — discarding",
                        self.manifest.name,
                        msg_id,
                    )
                    continue
                if not fut.done():
                    fut.set_result(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("MCP %s stdout reader crashed: %s", self.manifest.name, exc)
        finally:
            # Wake up any pending callers so they don't hang forever.
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(
                        MCPError(f"MCP {self.manifest.name!r}: stdout closed")
                    )

    async def _drain_stderr_loop(self) -> None:
        """Stream stderr to the logger so MCP crash details surface in our logs."""
        assert self._proc is not None and self._proc.stderr is not None
        stderr = self._proc.stderr
        child_logger = logger.getChild(f"mcp.{self.manifest.name}")
        try:
            while True:
                raw = await stderr.readline()
                if not raw:
                    break
                text = raw.decode("utf-8", errors="replace").rstrip()
                if text:
                    child_logger.info(text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.debug("MCP %s stderr reader stopped: %s", self.manifest.name, exc)


def _extract_text_content(content: Any) -> str:
    """Concatenate ``text`` parts from an MCP tool-result ``content`` array.

    MCP tool results return ``content: [{type: "text", text: "..."}, ...]``.
    Non-text parts (images, embedded resources) are summarized but not
    decoded — skills that need them should use a different tool.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return json.dumps(content, ensure_ascii=False, default=str)
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        kind = item.get("type")
        if kind == "text":
            parts.append(str(item.get("text") or ""))
        elif kind == "image":
            parts.append(f"[image:{item.get('mimeType') or 'unknown'}]")
        elif kind == "resource":
            uri = item.get("resource", {}).get("uri") if isinstance(item.get("resource"), dict) else None
            parts.append(f"[resource:{uri or 'embedded'}]")
        else:
            parts.append(json.dumps(item, ensure_ascii=False, default=str))
    return "\n".join(p for p in parts if p)


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
