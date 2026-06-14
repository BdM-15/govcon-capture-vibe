"""Tests for LangGraph Studio subprocess lifecycle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.server.langgraph_studio_lifecycle import (
    LangGraphStudioController,
    LangGraphStudioEndpoint,
    build_controller_from_env,
    find_available_studio_port,
    is_auto_start_enabled,
    is_tunnel_enabled,
    listener_pids_on_port,
    parse_public_api_url_from_log,
    studio_langsmith_enabled,
    studio_status_payload,
    studio_connect_hint,
    studio_ui_url,
    terminate_listeners_on_port,
    wait_for_studio,
)


def test_studio_ui_url_empty_when_api_missing() -> None:
    assert studio_ui_url("") == ""
    assert studio_ui_url("  ") == ""


def test_studio_status_payload_hides_graph_url_when_unavailable() -> None:
    payload = studio_status_payload(
        {
            "ok": False,
            "url": "http://127.0.0.1:2024",
            "graph_url": "https://smith.langchain.com/studio/?baseUrl=x",
            "error": "studio process exited (1)",
        }
    )
    assert payload["graph_url"] == ""
    assert payload["error"] == "studio process exited (1)"


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


def test_is_tunnel_enabled_defaults_false() -> None:
    assert is_tunnel_enabled({}) is False
    assert is_tunnel_enabled({"THESEUS_LANGGRAPH_STUDIO_TUNNEL": "true"}) is True


def test_graph_url_uses_localhost_not_tunnel() -> None:
    endpoint = LangGraphStudioEndpoint(
        host="127.0.0.1",
        port=2024,
        public_api_url="https://economics-minority-secret-voluntary.trycloudflare.com",
    )
    assert "127.0.0.1" in endpoint.graph_url
    assert "trycloudflare" not in endpoint.graph_url


def test_studio_connect_hint_local_vs_tunnel() -> None:
    assert "Local network access" in studio_connect_hint(tunnel=False)
    assert "Configure connection" in studio_connect_hint(
        tunnel=True,
        public_api_url="https://x.trycloudflare.com",
    )


def test_parse_public_api_url_from_log_finds_tunnel() -> None:
    from pathlib import Path
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as handle:
        handle.write("Starting Cloudflare Tunnel...\n")
        handle.write("https://abc-123.trycloudflare.com\n")
        path = Path(handle.name)
    try:
        assert parse_public_api_url_from_log(path) == "https://abc-123.trycloudflare.com"
    finally:
        path.unlink(missing_ok=True)


def test_find_available_studio_port_skips_listening_ports() -> None:
    port = find_available_studio_port(
        "127.0.0.1",
        2024,
        port_check=lambda _host, candidate: candidate == 2024,
    )
    assert port != 2024


def test_start_relocates_when_ghost_port_stays_open(monkeypatch) -> None:
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
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "src.server.langgraph_studio_lifecycle.wait_for_port_free",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "src.server.langgraph_studio_lifecycle.find_available_studio_port",
        lambda _host, _preferred, **kwargs: 2025,
    )

    endpoint = LangGraphStudioEndpoint(host="127.0.0.1", port=2024)
    controller = LangGraphStudioController(endpoint=endpoint, repo_root=Path("."))
    proc = MagicMock()
    proc.poll.return_value = None
    captured_cmd: list[str] = []

    def _popen(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return proc

    assert controller.start(
        port_check=lambda _host, _port: True,
        wait=lambda _endpoint, **_kwargs: True,
        popen=_popen,
        command_builder=lambda: ["langgraph"],
        tunnel_enabled=False,
    )
    assert controller.endpoint.port == 2025
    assert "--tunnel" not in captured_cmd


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
        assert "--tunnel" not in cmd
        return proc

    assert controller.start(
        port_check=lambda _host, _port: False,
        wait=lambda _endpoint, **_kwargs: True,
        popen=_popen,
        command_builder=lambda: ["langgraph"],
        tunnel_enabled=False,
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