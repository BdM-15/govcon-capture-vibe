"""Minimal MCP server used by tests/skills/test_mcp_session.py.

Speaks the slice of JSON-RPC that :class:`MCPSession` exercises:
``initialize`` + ``notifications/initialized`` + ``tools/list`` + ``tools/call``.
Newline-delimited JSON on stdin/stdout per the official MCP stdio spec.

Behavior is controlled by env vars so the test can probe error paths without
spawning multiple distinct binaries:

* ``THESEUS_FAKE_MCP_HANG=1``  — sleep forever in initialize (handshake timeout)
* ``THESEUS_FAKE_MCP_CRASH=1`` — exit before responding to initialize
* ``THESEUS_FAKE_MCP_BAD_TOOL=1`` — every tools/call returns isError=true

Otherwise the server exposes one tool, ``echo``, that returns its arguments
back as text content.
"""

from __future__ import annotations

import json
import os
import sys
import time


def _send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _read_message() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return _read_message()
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return _read_message()


def _handle(msg: dict) -> None:
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        if os.getenv("THESEUS_FAKE_MCP_HANG"):
            time.sleep(60)
            return
        if os.getenv("THESEUS_FAKE_MCP_CRASH"):
            sys.exit(7)
        _send(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-mcp", "version": "0.0.1"},
                },
            }
        )
        return

    if method == "notifications/initialized":
        return  # notification, no response

    if method == "tools/list":
        _send(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Echoes its 'text' argument back as content.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                },
                                "required": ["text"],
                            },
                        }
                    ]
                },
            }
        )
        return

    if method == "tools/call":
        params = msg.get("params") or {}
        args = params.get("arguments") or {}
        if os.getenv("THESEUS_FAKE_MCP_BAD_TOOL"):
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": "deliberate failure"}],
                    },
                }
            )
            return
        large_chars = os.getenv("THESEUS_FAKE_MCP_LARGE_ECHO_CHARS")
        if large_chars:
            text = "x" * int(large_chars)
        else:
            text = args.get("text", "")
        _send(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"echo:{text}"}],
                    "isError": False,
                },
            }
        )
        return

    if method == "shutdown":
        sys.exit(0)

    # Unknown method — return a JSON-RPC error.
    _send(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        }
    )


def main() -> None:
    while True:
        msg = _read_message()
        if msg is None:
            return
        _handle(msg)


if __name__ == "__main__":
    main()
