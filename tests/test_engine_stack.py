from __future__ import annotations

from src.server.engine_stack import (
    build_engine_stack_payload,
    mineru_versions_aligned,
    normalize_expected_version,
    resolve_mineru_stack_version,
)


def test_normalize_expected_version_expands_two_part_pins() -> None:
    assert normalize_expected_version("3.3") == "3.3.0"


def test_mineru_versions_aligned_accepts_newer_patch() -> None:
    assert mineru_versions_aligned("3.3.1", "3.3") is True
    assert mineru_versions_aligned("3.0.9", "3.3") is False


def test_resolve_mineru_stack_version_uses_env_target(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.server.engine_stack.resolve_installed_version",
        lambda _dist, **_: "3.3.1",
    )
    stack = resolve_mineru_stack_version("3.3")
    assert stack.expected == "3.3"
    assert stack.installed == "3.3.1"
    assert stack.aligned is True


def test_build_engine_stack_payload_includes_mineru_target_fields() -> None:
    payload = build_engine_stack_payload(mineru_expected="3.3")
    assert payload["mineru_expected"] == "3.3"
    assert "mineru_aligned" in payload
    assert "mineru" in payload
    assert "lightrag" in payload