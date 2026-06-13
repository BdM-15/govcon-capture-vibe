"""Pipeline library routes reflect runtime LangGraph Studio status."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.pipeline_routes import register_pipeline_routes
from src.server.runtime_state import clear_langgraph_studio_status, set_langgraph_studio_status


def _client() -> TestClient:
    app = FastAPI()
    register_pipeline_routes(app)
    return TestClient(app)


def test_pipeline_library_exposes_studio_when_runtime_ready() -> None:
    set_langgraph_studio_status(
        {
            "ok": True,
            "state": "ready",
            "url": "http://127.0.0.1:2024",
            "graph_url": "https://smith.langchain.com/studio/?baseUrl=http%3A//127.0.0.1%3A2024&graph=mission_readiness",
        }
    )
    try:
        response = _client().get("/api/ui/pipelines/library")
    finally:
        clear_langgraph_studio_status()

    assert response.status_code == 200
    body = response.json()
    assert body["studio_ready"] is True
    assert body["studio_auto_start"] is True
    assert body["studio_url"] == "http://127.0.0.1:2024"
    assert "smith.langchain.com/studio" in body["studio_graph_url"]
    assert body["pipelines"][0]["studio_graph_url"] == body["studio_graph_url"]
    assert "studio_cli" not in body["pipelines"][0]


def test_pipeline_library_hides_studio_link_when_offline() -> None:
    set_langgraph_studio_status(
        {
            "ok": False,
            "state": "unavailable",
            "url": "http://127.0.0.1:2024",
            "error": "studio unreachable",
        }
    )
    try:
        body = _client().get("/api/ui/pipelines/library").json()
    finally:
        clear_langgraph_studio_status()

    assert body["studio_ready"] is False
    assert body["studio_url"] == ""
    assert body["pipelines"][0]["studio_url"] == ""