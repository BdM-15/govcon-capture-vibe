from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.skill_routes import register_skill_catalog_ui_routes


class _SkillSummary:
    def __init__(self, payload):
        self._payload = payload

    def to_summary(self):
        return self._payload


class _FakeManager:
    def __init__(self):
        self.discover_calls = 0
        self.install_error = None
        self.uninstall_error = None
        self.uninstall_result = True

    def list_skills(self):
        return [{"name": "demo"}]

    def discover(self):
        self.discover_calls += 1

    def get_skill_detail(self, name: str):
        if name == "demo":
            return {"name": "demo", "detail": True}
        return None

    async def install_from_github(self, url: str, name=None):
        if self.install_error is not None:
            raise self.install_error
        return _SkillSummary({"name": name or "demo", "url": url})

    async def uninstall(self, name: str):
        if self.uninstall_error is not None:
            raise self.uninstall_error
        return self.uninstall_result


def _client(manager: _FakeManager) -> TestClient:
    app = FastAPI()
    register_skill_catalog_ui_routes(app, manager_factory=lambda: manager)
    return TestClient(app)


def test_skill_catalog_routes_success_path() -> None:
    manager = _FakeManager()
    client = _client(manager)

    listed = client.get("/api/ui/skills")
    assert listed.status_code == 200, listed.text
    assert listed.json() == {"skills": [{"name": "demo"}]}

    refreshed = client.post("/api/ui/skills/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert manager.discover_calls == 1

    detail = client.get("/api/ui/skills/demo")
    assert detail.status_code == 200, detail.text
    assert detail.json()["name"] == "demo"

    installed = client.post(
        "/api/ui/skills/install",
        json={"url": "https://github.com/org/repo", "name": "custom"},
    )
    assert installed.status_code == 200, installed.text
    assert installed.json() == {
        "skill": {"name": "custom", "url": "https://github.com/org/repo"}
    }

    removed = client.delete("/api/ui/skills/demo")
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"removed": "demo"}


def test_skill_catalog_routes_map_errors() -> None:
    manager = _FakeManager()
    client = _client(manager)

    missing = client.get("/api/ui/skills/nope")
    assert missing.status_code == 404

    manager.install_error = FileExistsError("exists")
    install_conflict = client.post(
        "/api/ui/skills/install",
        json={"url": "https://github.com/org/repo"},
    )
    assert install_conflict.status_code == 409

    manager.install_error = ValueError("bad url")
    install_bad = client.post(
        "/api/ui/skills/install",
        json={"url": "https://github.com/org/repo"},
    )
    assert install_bad.status_code == 400

    manager.uninstall_error = PermissionError("blocked")
    uninstall_blocked = client.delete("/api/ui/skills/demo")
    assert uninstall_blocked.status_code == 403

    manager.uninstall_error = None
    manager.uninstall_result = False
    uninstall_missing = client.delete("/api/ui/skills/demo")
    assert uninstall_missing.status_code == 404