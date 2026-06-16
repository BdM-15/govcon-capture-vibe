"""Tests for server freshness preflight."""

from __future__ import annotations

from pathlib import Path

from src.skills.ensure_theseus_server import ensure_theseus_server_fresh
from src.skills.server_code_fingerprint import compute_server_code_fingerprint


def test_compute_server_code_fingerprint_stable_same_tree() -> None:
    repo = Path(__file__).resolve().parents[2]
    first = compute_server_code_fingerprint(repo_root=repo)
    second = compute_server_code_fingerprint(repo_root=repo)
    assert first
    assert first == second


def test_ensure_server_fresh_reports_stale_without_restart(monkeypatch) -> None:
    repo = Path(__file__).resolve().parents[2]
    expected = compute_server_code_fingerprint(repo_root=repo)

    monkeypatch.setattr(
        "src.skills.ensure_theseus_server.fetch_server_fingerprint",
        lambda *_args, **_kwargs: "stale-fingerprint",
    )

    ok, message = ensure_theseus_server_fresh(
        repo_root=repo,
        restart=False,
    )
    assert not ok
    assert expected in message
    assert "stale" in message