"""Tests for src.server.mineru_lifecycle.

Cover the four behaviors that motivated issue #174:
- Required-when-route-includes-mineru.
- Skip-when-port-already-bound.
- Spawn-and-wait happy path.
- Stop-on-shutdown only when we started the process.
"""

from __future__ import annotations

import socket
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest

from src.server.mineru_lifecycle import (
    MineruController,
    MineruEndpoint,
    build_controller_from_env,
    is_mineru_required,
    is_port_listening,
    parse_mineru_endpoint,
    wait_for_mineru,
)


def test_parse_mineru_endpoint_handles_full_url_and_bare_hostport() -> None:
    assert parse_mineru_endpoint("http://localhost:8888") == MineruEndpoint("localhost", 8888)
    assert parse_mineru_endpoint("127.0.0.1:9000") == MineruEndpoint("127.0.0.1", 9000)


def test_is_mineru_required_only_when_route_and_local_mode() -> None:
    rules = "pdf:mineru-ite,docx:native-ite,xlsx:legacy"
    assert is_mineru_required(rules, "local") is True
    assert is_mineru_required(rules, "official") is False
    assert is_mineru_required("docx:native-ite,xlsx:legacy", "local") is False
    assert is_mineru_required(None, "local") is False


class _FakeSocket:
    def __init__(self, *, succeed: bool):
        self.succeed = succeed
        self.closed = False

    def settimeout(self, _t: float) -> None:
        return None

    def connect(self, _addr: tuple[str, int]) -> None:
        if not self.succeed:
            raise OSError("refused")

    def close(self) -> None:
        self.closed = True


def test_is_port_listening_returns_true_when_socket_connects() -> None:
    sock = _FakeSocket(succeed=True)
    assert is_port_listening("127.0.0.1", 8888, socket_factory=lambda: sock) is True
    assert sock.closed


def test_is_port_listening_returns_false_when_socket_refused() -> None:
    sock = _FakeSocket(succeed=False)
    assert is_port_listening("127.0.0.1", 8888, socket_factory=lambda: sock) is False
    assert sock.closed


def test_wait_for_mineru_returns_true_on_first_200() -> None:
    calls = {"open": 0, "sleep": 0}

    def opener(url: str, timeout: float):
        calls["open"] += 1
        return SimpleNamespace(status=200, close=lambda: None)

    ep = MineruEndpoint("127.0.0.1", 8888)
    ok = wait_for_mineru(
        ep,
        timeout=5.0,
        interval=0.1,
        url_opener=opener,
        sleep=lambda _t: calls.__setitem__("sleep", calls["sleep"] + 1),
        clock=lambda: 0.0,
    )
    assert ok is True
    assert calls["open"] == 1


def test_wait_for_mineru_times_out_when_never_ready() -> None:
    ticks = iter([0.0, 0.05, 0.1, 0.5, 1.5, 2.5])

    def opener(_url: str, _timeout: float):
        raise ConnectionError("nope")

    ep = MineruEndpoint("127.0.0.1", 8888)
    ok = wait_for_mineru(
        ep,
        timeout=1.0,
        interval=0.0,
        url_opener=opener,
        sleep=lambda _t: None,
        clock=lambda: next(ticks),
    )
    assert ok is False


class _FakeProc:
    def __init__(self) -> None:
        self.pid = 4242
        self.terminated = False
        self.killed = False
        self._poll = None

    def poll(self) -> Any:
        return self._poll

    def terminate(self) -> None:
        self.terminated = True
        self._poll = 0

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        self.killed = True
        self._poll = -9


def test_controller_skips_spawn_when_port_already_bound() -> None:
    controller = MineruController(endpoint=MineruEndpoint("127.0.0.1", 8888))
    proc = _FakeProc()

    def popen(_cmd):  # pragma: no cover - must not be called
        raise AssertionError("popen should not be called when port is bound")

    started = controller.start(
        popen=popen,  # type: ignore[arg-type]
        port_check=lambda _h, _p: True,
        wait=lambda _ep: True,
    )
    assert started is True
    assert controller.process is None
    assert controller.started_by_us is False
    controller.process = proc  # ensure stop() does nothing when not started_by_us
    controller.stop()
    assert proc.terminated is False


def test_controller_spawns_and_waits_then_stops() -> None:
    controller = MineruController(endpoint=MineruEndpoint("127.0.0.1", 8888))
    proc = _FakeProc()

    captured: dict[str, Any] = {}

    def popen(cmd):
        captured["cmd"] = cmd
        return proc

    started = controller.start(
        popen=popen,  # type: ignore[arg-type]
        port_check=lambda _h, _p: False,
        wait=lambda _ep: True,
    )
    assert started is True
    assert controller.started_by_us is True
    assert controller.process is proc
    assert "mineru.cli.fast_api" in " ".join(captured["cmd"])
    assert "--port" in captured["cmd"] and "8888" in captured["cmd"]

    controller.stop()
    assert proc.terminated is True
    assert controller.process is None


def test_controller_stops_subprocess_when_wait_times_out() -> None:
    controller = MineruController(endpoint=MineruEndpoint("127.0.0.1", 8888))
    proc = _FakeProc()

    started = controller.start(
        popen=lambda _cmd: proc,  # type: ignore[arg-type]
        port_check=lambda _h, _p: False,
        wait=lambda _ep: False,
    )
    assert started is False
    assert proc.terminated is True
    assert controller.process is None


def test_build_controller_from_env_returns_none_when_not_required() -> None:
    env = {"LIGHTRAG_PARSER": "docx:native-ite,xlsx:legacy", "MINERU_API_MODE": "local"}
    assert build_controller_from_env(env) is None


def test_build_controller_from_env_uses_local_endpoint() -> None:
    env = {
        "LIGHTRAG_PARSER": "pdf:mineru-ite",
        "MINERU_API_MODE": "local",
        "MINERU_LOCAL_ENDPOINT": "http://127.0.0.1:9999",
    }
    controller = build_controller_from_env(env)
    assert controller is not None
    assert controller.endpoint == MineruEndpoint("127.0.0.1", 9999)
