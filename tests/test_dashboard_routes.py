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
    (static / "index.html").write_text(
        "<html><body data-testid='theseus-app'>Ariadne's Thread</body></html>",
        encoding="utf-8",
    )
    return static


def test_dashboard_served_at_root(tmp_path: Path) -> None:
    app = FastAPI()
    register_dashboard_routes(app, static_dir=_write_static(tmp_path))
    client = TestClient(app)

    resp = client.get("/")
    assert resp.status_code == 200
    assert "theseus-app" in resp.text
    assert "Ariadne's Thread" in resp.text


def test_dashboard_overrides_existing_root_route(tmp_path: Path) -> None:
    app = FastAPI()

    @app.get("/")
    async def _legacy_root() -> RedirectResponse:
        return RedirectResponse(url="/webui")

    register_dashboard_routes(app, static_dir=_write_static(tmp_path))
    client = TestClient(app)

    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 200
    assert "theseus-app" in resp.text


def test_workspace_alias_serves_workbench(tmp_path: Path) -> None:
    app = FastAPI()
    register_dashboard_routes(app, static_dir=_write_static(tmp_path))
    client = TestClient(app)

    resp = client.get("/workspace/afcap6_drfp")
    assert resp.status_code == 200
    assert "theseus-app" in resp.text


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
    client = TestClient(app)

    paths = {route.path for route in app.routes}
    assert "/" in paths
    assert "/workspace/{name}" in paths

    resp = client.get("/ui/")
    assert resp.status_code == 200
    assert "Ariadne's Thread" in resp.text
    assert "data-testid=\"ariadne-dashboard\"" in resp.text
    # 174.4b: command-center IA — KPI strip + Morning Brief panel are mandatory.
    assert "data-testid=\"ariadne-kpi-strip\"" in resp.text
    assert "data-testid=\"ariadne-view-nav\"" in resp.text
    assert "data-testid=\"ariadne-view-today\"" in resp.text
    assert "data-testid=\"ariadne-today-focus\"" in resp.text
    assert "data-testid=\"ariadne-morning-brief\"" in resp.text
    assert "data-testid=\"ariadne-action-queue\"" in resp.text
    assert "data-testid=\"ariadne-pipeline-radar\"" in resp.text
    assert "data-testid=\"ariadne-pipeline-pressure\"" in resp.text
    assert "data-testid=\"ariadne-opportunity-cards\"" in resp.text
    assert "data-testid=\"ariadne-stage-board\"" in resp.text
    assert "data-testid=\"ariadne-view-decision-queue\"" in resp.text
    assert "data-testid=\"ariadne-decision-summary\"" in resp.text
    assert "data-testid=\"ariadne-view-intel-desk\"" in resp.text
    assert "data-testid=\"ariadne-intel-radar\"" in resp.text
    assert "data-testid=\"ariadne-pattern-feed\"" in resp.text
    assert "data-testid=\"ariadne-pattern-filters\"" in resp.text
    assert "data-testid=\"ariadne-view-opp-360\"" in resp.text
    assert "data-testid=\"ariadne-opp360-next-actions\"" in resp.text
    assert "data-testid=\"ariadne-opp360-solutioning\"" in resp.text
    assert "data-testid=\"ariadne-view-knowledge\"" in resp.text
    assert "data-testid=\"ariadne-knowledge-summary\"" in resp.text
    assert "data-testid=\"ariadne-requirements-fit-scores\"" in resp.text
    assert "data-testid=\"ariadne-knowledge-fit-seeds\"" in resp.text
    assert "data-testid=\"ariadne-promotion-roundtrip\"" in resp.text
    assert "data-testid=\"ariadne-promotion-actions\"" in resp.text
    assert "data-testid=\"ariadne-view-agent-ops\"" in resp.text
    assert "data-testid=\"ariadne-agent-ops-summary\"" in resp.text
    assert "data-testid=\"ariadne-agent-activity\"" in resp.text
    assert "Capture Command Center" in resp.text
