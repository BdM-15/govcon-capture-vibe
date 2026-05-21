"""Tests for the Phase 4a MCP client subsystem (manifest, session, registry)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from src.skills.mcp_client import (
    MCPError,
    MCPManifest,
    MCPRegistry,
    MCPStartupResult,
    MCPSession,
    discover_manifests,
    load_manifest,
)
from src.skills.tools import build_mcp_tool_specs


_THIS_DIR = Path(__file__).resolve().parent
_FAKE_SERVER = _THIS_DIR / "fake_mcp_server.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_manifest(dir_path: Path, **overrides) -> Path:
    """Write a theseus_manifest.json that runs our fake MCP server."""
    dir_path.mkdir(parents=True, exist_ok=True)
    body = {
        "name": dir_path.name,
        "description": "Fake MCP server for tests",
        "command": [sys.executable, str(_FAKE_SERVER)],
        "env_required": [],
        "env_optional": [],
        "license": "MIT",
    }
    body.update(overrides)
    path = dir_path / "theseus_manifest.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Manifest tests (no subprocess)
# ---------------------------------------------------------------------------


def test_load_manifest_happy(tmp_path: Path) -> None:
    _write_manifest(tmp_path / "fakey")
    manifest = load_manifest(tmp_path / "fakey" / "theseus_manifest.json")
    assert manifest.name == "fakey"
    assert manifest.command[0] == sys.executable
    assert manifest.cwd == (tmp_path / "fakey").resolve()


def test_load_manifest_rejects_missing_command(tmp_path: Path) -> None:
    bad = tmp_path / "broken"
    bad.mkdir()
    (bad / "theseus_manifest.json").write_text(
        json.dumps({"name": "broken"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="command"):
        load_manifest(bad / "theseus_manifest.json")


def test_load_manifest_rejects_missing_name(tmp_path: Path) -> None:
    bad = tmp_path / "noname"
    bad.mkdir()
    (bad / "theseus_manifest.json").write_text(
        json.dumps({"command": ["echo"]}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="name"):
        load_manifest(bad / "theseus_manifest.json")


def test_load_manifest_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path / "nope.json")


def test_discover_skips_malformed(tmp_path: Path) -> None:
    _write_manifest(tmp_path / "good")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "theseus_manifest.json").write_text("not json", encoding="utf-8")
    # Directory without a manifest at all is silently skipped.
    (tmp_path / "nomanifest").mkdir()
    found = discover_manifests(tmp_path)
    assert set(found) == {"good"}


def test_missing_env_check() -> None:
    manifest = MCPManifest(
        name="x",
        description="",
        command=["true"],
        cwd=Path("."),
        env_required=["NEEDED_KEY"],
    )
    assert manifest.missing_env({"OTHER": "1"}) == ["NEEDED_KEY"]
    assert manifest.missing_env({"NEEDED_KEY": "v"}) == []


# ---------------------------------------------------------------------------
# Session tests (real subprocess via fake_mcp_server.py)
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine synchronously without requiring pytest-asyncio.

    A fresh event loop per test keeps subprocess state cleanly isolated.
    """
    return asyncio.new_event_loop().run_until_complete(coro)


def test_session_full_lifecycle(tmp_path: Path) -> None:
    async def _go():
        _write_manifest(tmp_path / "fakey")
        manifest = load_manifest(tmp_path / "fakey" / "theseus_manifest.json")
        session = MCPSession(manifest)
        try:
            await session.start()
            names = [t.name for t in session.tools]
            assert names == ["echo"]
            ns = session.tools[0].namespaced_name
            assert ns == "mcp__fakey__echo"
            out = await session.call_tool("echo", {"text": "hi"})
            assert out == "echo:hi"
        finally:
            await session.shutdown()

    _run(_go())


def test_session_tool_error_surfaces(tmp_path: Path, monkeypatch) -> None:
    async def _go():
        _write_manifest(tmp_path / "badtool")
        manifest = load_manifest(tmp_path / "badtool" / "theseus_manifest.json")
        monkeypatch.setenv("THESEUS_FAKE_MCP_BAD_TOOL", "1")
        session = MCPSession(manifest)
        try:
            await session.start()
            with pytest.raises(MCPError, match="deliberate failure"):
                await session.call_tool("echo", {"text": "x"})
        finally:
            await session.shutdown()

    _run(_go())


def test_session_handles_large_json_rpc_lines(tmp_path: Path, monkeypatch) -> None:
    async def _go():
        _write_manifest(tmp_path / "large")
        manifest = load_manifest(tmp_path / "large" / "theseus_manifest.json")
        monkeypatch.setenv("THESEUS_FAKE_MCP_LARGE_ECHO_CHARS", "200000")
        session = MCPSession(manifest)
        try:
            await session.start()
            out = await session.call_tool("echo", {"text": "ignored"})
            assert out == "echo:" + ("x" * 200000)
        finally:
            await session.shutdown()

    _run(_go())


def test_session_shutdown_idempotent(tmp_path: Path) -> None:
    async def _go():
        _write_manifest(tmp_path / "fakey")
        manifest = load_manifest(tmp_path / "fakey" / "theseus_manifest.json")
        session = MCPSession(manifest)
        await session.start()
        await session.shutdown()
        await session.shutdown()  # must not raise

    _run(_go())


def test_session_call_after_shutdown_raises(tmp_path: Path) -> None:
    async def _go():
        _write_manifest(tmp_path / "fakey")
        manifest = load_manifest(tmp_path / "fakey" / "theseus_manifest.json")
        session = MCPSession(manifest)
        await session.start()
        await session.shutdown()
        with pytest.raises(MCPError):
            await session.call_tool("echo", {"text": "x"})

    _run(_go())


def test_session_missing_required_env(tmp_path: Path) -> None:
    async def _go():
        _write_manifest(tmp_path / "needkey", env_required=["MUST_BE_SET"])
        manifest = load_manifest(tmp_path / "needkey" / "theseus_manifest.json")
        session = MCPSession(manifest)
        os.environ.pop("MUST_BE_SET", None)
        with pytest.raises(MCPError, match="missing required env"):
            await session.start()

    _run(_go())


def test_session_missing_executable(tmp_path: Path) -> None:
    async def _go():
        _write_manifest(
            tmp_path / "missing",
            command=["this-binary-definitely-does-not-exist-9c71"],
        )
        manifest = load_manifest(tmp_path / "missing" / "theseus_manifest.json")
        session = MCPSession(manifest)
        with pytest.raises(MCPError, match="not found"):
            await session.start()

    _run(_go())


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_registry_starts_only_requested(tmp_path: Path) -> None:
    async def _go():
        _write_manifest(tmp_path / "alpha")
        _write_manifest(tmp_path / "beta")
        registry = MCPRegistry.from_root(tmp_path)
        assert set(registry.known_mcps) == {"alpha", "beta"}
        result = await registry.start_run_sessions(
            run_id="run-1", requested=["alpha"]
        )
        try:
            assert set(result.sessions) == {"alpha"}
            assert result.missing == []
            assert result.failed == {}
            assert result.started_names == ["alpha"]
            assert result.sessions["alpha"].tools[0].name == "echo"
        finally:
            await registry.shutdown_run("run-1")

    _run(_go())


def test_registry_skips_unknown_mcp(tmp_path: Path) -> None:
    async def _go():
        _write_manifest(tmp_path / "alpha")
        registry = MCPRegistry.from_root(tmp_path)
        result = await registry.start_run_sessions(
            run_id="run-x", requested=["alpha", "does-not-exist"]
        )
        try:
            assert set(result.sessions) == {"alpha"}
            assert result.missing == ["does-not-exist"]
            assert result.failed == {}
        finally:
            await registry.shutdown_run("run-x")

    _run(_go())


def test_registry_empty_request(tmp_path: Path) -> None:
    async def _go():
        registry = MCPRegistry.from_root(tmp_path)
        result = await registry.start_run_sessions(run_id="r", requested=[])
        assert result.sessions == {}
        assert result.missing == []
        assert result.failed == {}

    _run(_go())


def test_registry_records_startup_failure(tmp_path: Path) -> None:
    async def _go():
        _write_manifest(tmp_path / "needkey", env_required=["MUST_BE_SET"])
        registry = MCPRegistry.from_root(tmp_path)
        os.environ.pop("MUST_BE_SET", None)
        result = await registry.start_run_sessions(
            run_id="r", requested=["needkey"]
        )
        assert result.sessions == {}
        assert result.missing == []
        assert set(result.failed) == {"needkey"}
        assert "missing required env" in result.failed["needkey"]

    _run(_go())


def test_startup_result_warning_messages() -> None:
    result = MCPStartupResult(
        missing=["unknown"],
        failed={"bad": "boom"},
    )

    assert result.warning_messages() == [
        "MCP servers requested but not installed: ['unknown']",
        "MCP servers failed to start: {'bad': 'boom'}",
    ]


def test_registry_shutdown_run_idempotent(tmp_path: Path) -> None:
    async def _go():
        _write_manifest(tmp_path / "alpha")
        registry = MCPRegistry.from_root(tmp_path)
        await registry.start_run_sessions(run_id="r", requested=["alpha"])
        await registry.shutdown_run("r")
        await registry.shutdown_run("r")  # second call is a no-op
        await registry.shutdown_run("never-existed")

    _run(_go())


# ---------------------------------------------------------------------------
# Tool-spec adapter (the bridge into runtime)
# ---------------------------------------------------------------------------


def test_build_mcp_tool_specs_round_trip(tmp_path: Path) -> None:
    async def _go():
        _write_manifest(tmp_path / "alpha")
        registry = MCPRegistry.from_root(tmp_path)
        result = await registry.start_run_sessions(run_id="r", requested=["alpha"])
        try:
            specs = build_mcp_tool_specs(result.sessions)
            names = [s.name for s in specs]
            assert names == ["mcp__alpha__echo"]

            from src.skills.tools import ToolContext

            ctx = ToolContext(
                skill_name="t",
                skill_dir=tmp_path,
                run_dir=tmp_path,
                workspace_dir=tmp_path,
                workspace_name="t",
            )
            result = await specs[0].handler(ctx, text="hello")
            assert result.payload["content"] == "echo:hello"
            assert result.payload["server"] == "alpha"
            assert result.payload["tool"] == "echo"
        finally:
            await registry.shutdown_run("r")

    _run(_go())


# ---------------------------------------------------------------------------
# Manager.required_mcps property (Phase 4b)
# ---------------------------------------------------------------------------


def test_required_mcps_parsed_from_metadata() -> None:
    from src.skills.manager import SkillFrontmatter

    fm = SkillFrontmatter(
        name="x",
        description="",
        metadata={"mcps": ["usaspending", "sam_gov"]},
    )
    assert fm.required_mcps == ["usaspending", "sam_gov"]


def test_required_mcps_accepts_string() -> None:
    from src.skills.manager import SkillFrontmatter

    fm = SkillFrontmatter(name="x", description="", metadata={"mcps": "usaspending"})
    assert fm.required_mcps == ["usaspending"]


def test_required_mcps_default_empty() -> None:
    from src.skills.manager import SkillFrontmatter

    fm = SkillFrontmatter(name="x", description="")
    assert fm.required_mcps == []
