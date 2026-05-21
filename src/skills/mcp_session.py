"""MCP session transport: subprocess lifecycle, JSON-RPC, tool calls."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from typing import Any, Optional

from src.skills.mcp_manifest import MCPManifest
from src.skills.mcp_protocol import (
    MCPToolDescriptor,
    extract_text_content,
    parse_tool_descriptors,
)
from src.skills.settings import (
    mcp_handshake_timeout,
    mcp_shutdown_timeout,
    mcp_stdio_buffer_limit,
    mcp_tool_call_timeout,
)

logger = logging.getLogger(__name__)

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
                limit=mcp_stdio_buffer_limit(),
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
