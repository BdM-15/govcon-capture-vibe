"""Tests for the Ariadne's Thread dashboard routes (174.4)."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

from src.server.dashboard_routes import register_dashboard_routes
from src.server.ui_routes import register_ui


def _write_static(tmp_path: Path) -> Path:
    static = tmp_path / "static"
    static.mkdir()
    (static / "dashboard.html").write_text(
        "<html><body data-testid='ariadne-dashboard'>ariadne</body></html>",
        encoding="utf-8",
    )
    (static / "index.html").write_text(
        "<html><body data-testid='workbench'>workbench</body></html>",
        encoding="utf-8",
    )
    return static


def test_dashboard_served_at_root(tmp_path: Path) -> None:
    app = FastAPI()
    register_dashboard_routes(app, static_dir=_write_static(tmp_path))
    client = TestClient(app)

    resp = client.get("/")
    assert resp.status_code == 200
    assert "ariadne-dashboard" in resp.text


def test_dashboard_overrides_existing_root_route(tmp_path: Path) -> None:
    app = FastAPI()

    @app.get("/")
    async def _legacy_root() -> RedirectResponse:
        return RedirectResponse(url="/webui")

    register_dashboard_routes(app, static_dir=_write_static(tmp_path))
    client = TestClient(app)

    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 200
    assert "ariadne-dashboard" in resp.text


def test_workspace_alias_serves_workbench(tmp_path: Path) -> None:
    app = FastAPI()
    register_dashboard_routes(app, static_dir=_write_static(tmp_path))
    client = TestClient(app)

    resp = client.get("/workspace/afcap6_drfp")
    assert resp.status_code == 200
    assert "workbench" in resp.text


def test_dashboard_served_at_ui_path(tmp_path: Path) -> None:
    """`/ui` and `/ui/` (legacy workbench URL) now serve the Ariadne dashboard."""
    app = FastAPI()
    register_dashboard_routes(app, static_dir=_write_static(tmp_path))
    client = TestClient(app)

    for path in ("/ui", "/ui/"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "ariadne-dashboard" in resp.text, path


def test_dashboard_routes_skipped_when_html_missing(tmp_path: Path) -> None:
    app = FastAPI()
    static = tmp_path / "static"
    static.mkdir()
    register_dashboard_routes(app, static_dir=static)

    paths = {route.path for route in app.routes}
    assert "/" not in paths
    assert "/workspace/{name}" not in paths


async def _stub_query(_text: str, _mode: str, _history: list[dict], _stream: bool, _overrides: dict):
    return "ok"


def test_register_ui_mounts_dashboard() -> None:
    app = FastAPI()
    register_ui(app, query_func=_stub_query)

    paths = {route.path for route in app.routes}
    assert "/" in paths
    assert "/ui" in paths
    assert "/ui/" in paths
    assert "/workspace/{name}" in paths
