from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.web_research_routes import register_web_research_settings_routes


def _client(tmp_path) -> TestClient:
    app = FastAPI()
    register_web_research_settings_routes(
        app,
        workspace_dir=lambda: tmp_path,
        workspace_name=lambda: "ws-a",
    )
    return TestClient(app)


def test_web_research_settings_routes_round_trip(tmp_path) -> None:
    client = _client(tmp_path)

    initial = client.get("/api/ui/settings/web-research")
    assert initial.status_code == 200, initial.text
    body = initial.json()
    assert body["workspace"] == "ws-a"
    assert body["settings"]["enabled"] is True
    assert body["settings"]["enable_firecrawl"] is False
    assert "providers" in body

    updated = client.put(
        "/api/ui/settings/web-research",
        json={"enable_firecrawl": True, "max_search_results": 6},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["settings"]["enable_firecrawl"] is True
    assert updated.json()["settings"]["max_search_results"] == 6
    assert updated.json()["providers"]["policy"]["firecrawl_global_enabled"] is True

    reset = client.post("/api/ui/settings/web-research/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["settings"]["enable_firecrawl"] is False