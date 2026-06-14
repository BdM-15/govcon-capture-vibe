"""LangSmith env normalization and connectivity helpers."""

from __future__ import annotations

from src.server.langsmith_runtime import (
    apply_langsmith_env,
    langsmith_configured,
    langsmith_stats_payload,
    studio_subprocess_env,
    verify_langsmith_connection,
)


def test_apply_langsmith_env_mirrors_key_and_project() -> None:
    env = apply_langsmith_env(
        {},
        source={
            "LANGSMITH_API_KEY": "lsv2_pt_test",
            "LANGSMITH_PROJECT": "demo-project",
        },
    )
    assert env["LANGSMITH_API_KEY"] == "lsv2_pt_test"
    assert env["LANGCHAIN_API_KEY"] == "lsv2_pt_test"
    assert env["LANGSMITH_PROJECT"] == "demo-project"
    assert env["LANGCHAIN_PROJECT"] == "demo-project"
    assert env["LANGSMITH_TRACING"] == "true"
    assert env["LANGCHAIN_TRACING_V2"] == "true"


def test_langsmith_configured_detects_key() -> None:
    assert langsmith_configured({"LANGSMITH_API_KEY": "x"}) is True
    assert langsmith_configured({}) is False


def test_verify_langsmith_connection_without_key() -> None:
    payload = verify_langsmith_connection(env={})
    assert payload["ok"] is False
    assert payload["state"] == "unconfigured"


def test_verify_langsmith_connection_uses_client_factory() -> None:
    class _Project:
        name = "demo"

    class _Client:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

        def list_projects(self, limit: int = 5):
            assert limit == 5
            return [_Project()]

    payload = verify_langsmith_connection(
        env={"LANGSMITH_API_KEY": "lsv2_pt_test", "LANGSMITH_PROJECT": "demo"},
        client_factory=_Client,
    )
    assert payload["ok"] is True
    assert payload["workspace_projects"] == 1


def test_studio_subprocess_env_sets_utf8_on_windows() -> None:
    env = studio_subprocess_env({})
    assert env.get("PYTHONUTF8") == "1"
    assert env.get("PYTHONIOENCODING") == "utf-8"


def test_langsmith_stats_payload_shapes_ui_row() -> None:
    row = langsmith_stats_payload(
        {"ok": True, "state": "connected", "project": "theseus-mission-readiness", "tracing": True}
    )
    assert row["ok"] is True
    assert row["project"] == "theseus-mission-readiness"