"""Tests for LangGraph Studio subprocess lifecycle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.server.langgraph_studio_lifecycle import (
    LangGraphStudioController,
    LangGraphStudioEndpoint,
    build_controller_from_env,
    is_auto_start_enabled,
    listener_pids_on_port,
    studio_langsmith_enabled,
    studio_status_payload,
    terminate_listeners_on_port,
    wait_for_studio,
)


def test_is_auto_start_enabled_defaults_true() -> None:
    assert is_auto_start_enabled({}) is True
    assert is_auto_start_enabled({"THESEUS_LANGGRAPH_STUDIO_AUTO_START": "true"}) is True
    assert is_auto_start_enabled({"THESEUS_LANGGRAPH_STUDIO_AUTO_START": "false"}) is False


def test_build_controller_from_env_when_disabled() -> None:
    assert build_controller_from_env({"THESEUS_LANGGRAPH_STUDIO_AUTO_START": "off"}) is None


def test_build_controller_from_env_requires_langsmith_key() -> None:
    assert build_controller_from_env(
        {"THESEUS_LANGGRAPH_STUDIO_AUTO_START": "true", "LANGGRAPH_STUDIO_PORT": "2024"}
    ) is None


def test_build_controller_from_env_when_enabled() -> None:
    controller = build_controller_from_env(
        {
            "THESEUS_LANGGRAPH_STUDIO_AUTO_START": "true",
            "LANGGRAPH_STUDIO_PORT": "2024",
            "LANGSMITH_API_KEY": "lsv2_pt_test",
        }
    )
    assert controller is not None
    assert controller.endpoint.port == 2024


def test_start_reuses_existing_listener_without_spawn(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.server.langgraph_studio_lifecycle.fetch_studio_info",
        lambda _endpoint: {"flags": {"langsmith": True}},
    )
    monkeypatch.setattr(
        "src.server.langgraph_studio_lifecycle.langsmith_configured",
        lambda *_args, **_kwargs: True,
    )
    endpoint = LangGraphStudioEndpoint(host="127.0.0.1", port=2024)
    controller = LangGraphStudioController(endpoint=endpoint, repo_root=Path("."))
    assert controller.start(
        port_check=lambda _host, _port: True,
        wait=lambda _endpoint, **_kwargs: True,
        popen=MagicMock(),
    )
    assert controller.started_by_us is False
    assert controller.process is None


def test_start_recycles_listener_missing_langsmith_key(monkeypatch) -> None:
    killed: list[int] = []
    info_calls = {"count": 0}

    def _info(_endpoint):
        info_calls["count"] += 1
        enabled = info_calls["count"] > 1
        return {"flags": {"langsmith": enabled}}

    monkeypatch.setattr(
        "src.server.langgraph_studio_lifecycle.fetch_studio_info",
        _info,
    )
    monkeypatch.setattr(
        "src.server.langgraph_studio_lifecycle.langsmith_configured",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "src.server.langgraph_studio_lifecycle.terminate_listeners_on_port",
        lambda _port, **kwargs: killed.append(1) or [999],
    )
    monkeypatch.setattr(
        "src.server.langgraph_studio_lifecycle.wait_for_port_free",
        lambda *_args, **_kwargs: True,
    )

    endpoint = LangGraphStudioEndpoint(host="127.0.0.1", port=2024)
    controller = LangGraphStudioController(endpoint=endpoint, repo_root=Path("."))
    proc = MagicMock()
    proc.poll.return_value = None

    calls = {"port": 0}

    def _port_check(_host, _port):
        calls["port"] += 1
        return calls["port"] == 1

    assert controller.start(
        port_check=_port_check,
        wait=lambda _endpoint, **_kwargs: True,
        popen=lambda *_args, **_kwargs: proc,
        command_builder=lambda: ["langgraph"],
    )
    assert killed == [1]
    assert controller.started_by_us is True


def test_studio_langsmith_enabled_reads_info_flags() -> None:
    assert studio_langsmith_enabled({"flags": {"langsmith": True}}) is True
    assert studio_langsmith_enabled({"flags": {"langsmith": False}}) is False


def test_listener_pids_on_port_parses_netstat() -> None:
    class _Result:
        stdout = "TCP    127.0.0.1:2024    0.0.0.0:0    LISTENING    4242\n"

    pids = listener_pids_on_port(
        2024,
        netstat_runner=lambda *_args, **_kwargs: _Result(),
    )
    assert pids == [4242]


def test_start_spawns_when_port_closed() -> None:
    endpoint = LangGraphStudioEndpoint(host="127.0.0.1", port=2024)
    controller = LangGraphStudioController(endpoint=endpoint, repo_root=Path("."))
    proc = MagicMock()
    proc.poll.return_value = None

    def _popen(cmd, **kwargs):
        assert "dev" in cmd
        assert "--no-browser" in cmd
        assert "--no-reload" in cmd
        return proc

    assert controller.start(
        port_check=lambda _host, _port: False,
        wait=lambda _endpoint, **_kwargs: True,
        popen=_popen,
        command_builder=lambda: ["langgraph"],
    )
    assert controller.started_by_us is True
    assert controller.process is proc


def test_wait_for_studio_accepts_http_200() -> None:
    endpoint = LangGraphStudioEndpoint(host="127.0.0.1", port=2024)

    class _Resp:
        status = 200

        def getcode(self):
            return 200

        def close(self):
            return None

    assert wait_for_studio(
        endpoint,
        timeout=1.0,
        interval=0.01,
        url_opener=lambda _url, _to: _Resp(),
        sleep=lambda _s: None,
        clock=lambda: 0.0,
    )


def test_studio_status_payload_ready() -> None:
    payload = studio_status_payload(
        {
            "ok": True,
            "url": "http://127.0.0.1:2024",
            "version": "1.2.5",
            "started_by_us": True,
        }
    )
    assert payload["ok"] is True
    assert payload["url"] == "http://127.0.0.1:2024"