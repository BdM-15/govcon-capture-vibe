"""MCP session transport: subprocess lifecycle, JSON-RPC, tool calls."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.skills.settings import (
    mcp_handshake_timeout,
    mcp_shutdown_timeout,
    mcp_tool_call_timeout,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol helpers (inlined from mcp_protocol)
# ---------------------------------------------------------------------------

_TOOL_NAME_MAX = 64


@dataclass
class MCPToolDescriptor:
    """An MCP-discovered tool, ready to be wrapped into a ToolSpec."""

    server: str
    name: str
    description: str
    input_schema: dict[str, Any]

    @property
    def namespaced_name(self) -> str:
        candidate = f"mcp__{self.server}__{self.name}"
        if len(candidate) > _TOOL_NAME_MAX:
            candidate = candidate[:_TOOL_NAME_MAX]
        return candidate


def parse_tool_descriptors(
    server_name: str,
    raw_tools: list[Any],
) -> list[MCPToolDescriptor]:
    """Normalize ``tools/list`` payload entries into descriptors."""
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
                server=server_name,
                name=name,
                description=str(entry.get("description") or "").strip(),
                input_schema=schema,
            )
        )
    return descriptors


def extract_text_content(content: Any) -> str:
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
            resource = item.get("resource")
            uri = resource.get("uri") if isinstance(resource, dict) else None
            parts.append(f"[resource:{uri or 'embedded'}]")
        else:
            parts.append(json.dumps(item, ensure_ascii=False, default=str))
    return "\n".join(part for part in parts if part)


# ---------------------------------------------------------------------------
# Manifest helpers (inlined from mcp_manifest)
# ---------------------------------------------------------------------------


@dataclass
class MCPManifest:
    """Theseus-side description of a vendored MCP server."""

    name: str
    description: str
    command: list[str]
    cwd: Path
    env_required: list[str] = field(default_factory=list)
    env_optional: list[str] = field(default_factory=list)
    vendored_from: str = ""
    vendored_commit: str = ""
    vendored_at: str = ""
    license: str = ""

    def missing_env(self, env: Optional[dict[str, str]] = None) -> list[str]:
        """Return required env vars absent from env or os.environ."""
        scope = env if env is not None else os.environ
        return [key for key in self.env_required if not scope.get(key)]


def load_manifest(manifest_path: Path) -> MCPManifest:
    """Parse tools/mcps/<name>/theseus_manifest.json."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"manifest {manifest_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"manifest {manifest_path}: top-level must be a JSON object")
    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError(f"manifest {manifest_path}: missing 'name'")
    command = raw.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(entry, str) for entry in command):
        raise ValueError(
            f"manifest {manifest_path}: 'command' must be a non-empty list of strings"
        )
    return MCPManifest(
        name=name,
        description=str(raw.get("description") or ""),
        command=list(command),
        cwd=manifest_path.parent.resolve(),
        env_required=[str(entry) for entry in (raw.get("env_required") or [])],
        env_optional=[str(entry) for entry in (raw.get("env_optional") or [])],
        vendored_from=str(raw.get("vendored_from") or ""),
        vendored_commit=str(raw.get("vendored_commit") or ""),
        vendored_at=str(raw.get("vendored_at") or ""),
        license=str(raw.get("license") or ""),
    )


def discover_manifests(mcps_root: Path) -> dict[str, MCPManifest]:
    """Scan tools/mcps/*/theseus_manifest.json into a name -> manifest map."""
    found: dict[str, MCPManifest] = {}
    if not mcps_root.is_dir():
        logger.debug("MCP root %s does not exist; no manifests loaded", mcps_root)
        return found
    for child in sorted(mcps_root.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "theseus_manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = load_manifest(manifest_path)
        except (ValueError, FileNotFoundError) as exc:
            logger.warning("Skipping MCP at %s: %s", child, exc)
            continue
        if manifest.name in found:
            logger.warning(
                "Duplicate MCP name %r (second copy at %s) — keeping first",
                manifest.name,
                child,
            )
            continue
        found[manifest.name] = manifest
    return found


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

_MCP_PROTOCOL_VERSION = "2025-06-18"


class MCPError(Exception):
    """Raised for any MCP-side failure (spawn, handshake, call, shutdown)."""


class MCPSession:
    """One running MCP subprocess + JSON-RPC client."""

    def __init__(self, manifest: MCPManifest):
        self.manifest = manifest
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._stderr_task: Optional[asyncio.Task[None]] = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._tools: list[MCPToolDescriptor] = []
        self._closed = False

    async def start(self, env_extra: Optional[dict[str, str]] = None) -> None:
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)
        missing = self.manifest.missing_env(env)
        if missing:
            raise MCPError(
                f"MCP {self.manifest.name!r} missing required env vars: {missing}"
            )

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
                f"MCP {self.manifest.name!r}: executable not found ({exe}). Check theseus_manifest.json command[0] and PATH."
            ) from exc
        except OSError as exc:
            raise MCPError(f"MCP {self.manifest.name!r}: spawn failed: {exc}") from exc

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
            self._tools = await asyncio.wait_for(self._fetch_tools(), timeout=handshake_timeout)
        except asyncio.TimeoutError as exc:
            await self.shutdown()
            raise MCPError(
                f"MCP {self.manifest.name!r}: handshake/tool-list timed out after {handshake_timeout}s"
            ) from exc
        except MCPError:
            await self.shutdown()
            raise
        logger.info(
            "MCP %s started: %d tools (%s)",
            self.manifest.name,
            len(self._tools),
            ", ".join(tool.name for tool in self._tools[:6]) + ("…" if len(self._tools) > 6 else ""),
        )

    async def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True

        proc = self._proc
        if proc is not None and proc.returncode is None:
            try:
                await self._send({"jsonrpc": "2.0", "method": "shutdown"})
            except Exception:
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
                except (asyncio.CancelledError, Exception):
                    pass

        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(MCPError(f"MCP {self.manifest.name!r}: session closed"))
        self._pending.clear()

    @property
    def tools(self) -> list[MCPToolDescriptor]:
        return list(self._tools)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
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
                f"MCP {self.manifest.name!r}: tool {tool_name!r} timed out after {timeout}s"
            ) from exc

        result = response.get("result") or {}
        is_error = bool(result.get("isError"))
        text = extract_text_content(result.get("content"))
        if is_error:
            raise MCPError(
                f"MCP {self.manifest.name!r} tool {tool_name!r} returned an error: {text or '(no detail)'}"
            )
        return text

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
            raise MCPError(f"MCP {self.manifest.name!r}: initialize error: {response['error']}")
        await self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    async def _fetch_tools(self) -> list[MCPToolDescriptor]:
        response = await self._request("tools/list", {})
        if "error" in response:
            raise MCPError(f"MCP {self.manifest.name!r}: tools/list error: {response['error']}")
        result = response.get("result") or {}
        raw_tools = result.get("tools") or []
        return parse_tool_descriptors(self.manifest.name, raw_tools)

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._proc is None:
            raise MCPError(f"MCP {self.manifest.name!r}: not started")
        self._next_id += 1
        msg_id = self._next_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        try:
            await self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
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
        assert self._proc is not None and self._proc.stdout is not None
        stdout = self._proc.stdout
        try:
            while True:
                raw = await stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("MCP %s: malformed JSON on stdout: %r", self.manifest.name, line[:200])
                    continue
                if not isinstance(message, dict):
                    continue
                msg_id = message.get("id")
                if msg_id is None:
                    method = message.get("method")
                    if method:
                        logger.debug("MCP %s server notification: %s", self.manifest.name, method)
                    continue
                future = self._pending.get(int(msg_id))
                if future is None:
                    logger.debug("MCP %s: response for unknown id %s — discarding", self.manifest.name, msg_id)
                    continue
                if not future.done():
                    future.set_result(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("MCP %s stdout reader crashed: %s", self.manifest.name, exc)
        finally:
            for future in list(self._pending.values()):
                if not future.done():
                    future.set_exception(MCPError(f"MCP {self.manifest.name!r}: stdout closed"))

    async def _drain_stderr_loop(self) -> None:
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
        except Exception as exc:
            logger.debug("MCP %s stderr reader stopped: %s", self.manifest.name, exc)
