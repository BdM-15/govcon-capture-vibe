from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.skill_routes import register_skill_settings_ui_routes
from src.skills.settings import SkillSettingsStore


def _client(tmp_path, *, workspace: str = "demo", set_env_var=None) -> TestClient:
    app = FastAPI()
    register_skill_settings_ui_routes(
        app,
        settings_store=SkillSettingsStore(lambda: tmp_path),
        workspace_name=lambda: workspace,
        set_env_var=set_env_var,
    )
    return TestClient(app)


def test_skill_settings_routes_round_trip(tmp_path) -> None:
    client = _client(tmp_path, workspace="ws-a")

    initial = client.get("/api/ui/settings/skills")
    assert initial.status_code == 200, initial.text
    assert initial.json()["workspace"] == "ws-a"
    assert initial.json()["settings"]["retrieval_mode"] == "mix"

    updated = client.put(
        "/api/ui/settings/skills",
        json={"retrieval_mode": "HYBRID", "retrieval_top_k": 12},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["settings"]["retrieval_mode"] == "hybrid"
    assert updated.json()["settings"]["retrieval_top_k"] == 12

    reset = client.post("/api/ui/settings/skills/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["settings"]["retrieval_mode"] == "mix"


def test_skill_settings_routes_reject_bad_mode(tmp_path) -> None:
    client = _client(tmp_path)

    response = client.put(
        "/api/ui/settings/skills",
        json={"retrieval_mode": "bogus"},
    )

    assert response.status_code == 400
    assert "Unsupported retrieval_mode" in response.text


def test_skill_runtime_settings_routes_round_trip(tmp_path, monkeypatch) -> None:
    client = _client(
        tmp_path,
        workspace="ws-a",
        set_env_var=lambda key, value: monkeypatch.setenv(key, value),
    )

    initial = client.get("/api/ui/settings/skills/runtime")
    assert initial.status_code == 200, initial.text
    assert initial.json()["workspace"] == "ws-a"
    assert initial.json()["settings"]["max_turns"] == 20

    updated = client.put(
        "/api/ui/settings/skills/runtime",
        json={"max_turns": 21, "llm_timeout_seconds": 180, "max_kg_chunks": 44},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()["settings"]
    assert body["max_turns"] == 21
    assert body["llm_timeout_seconds"] == 180.0
    assert body["max_kg_chunks"] == 44

    reset = client.post("/api/ui/settings/skills/runtime/reset")
    assert reset.status_code == 200, reset.text
    assert reset.json()["settings"]["max_turns"] == 20
    assert reset.json()["settings"]["llm_timeout_seconds"] == 180.0


def test_skill_runtime_settings_routes_require_env_writer(tmp_path) -> None:
    client = _client(tmp_path)

    response = client.put(
        "/api/ui/settings/skills/runtime",
        json={"max_turns": 18},
    )

    assert response.status_code == 503