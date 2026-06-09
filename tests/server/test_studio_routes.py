"""Contract tests for thin Studio HTTP adapters (#188).

Studio routes must delegate filesystem semantics to ``SkillRunStore``,
not ``SkillManager`` pass-through methods.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core import get_settings
from src.skills.runs import SkillRunStore


def _seed_deliverable(workspace: Path, *, skill: str, run_id: str, filename: str) -> None:
    run_dir = workspace / "skill_runs" / skill / run_id
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (run_dir / "run.md").write_text(
        f"---\nrun_id: {run_id}\nskill: {skill}\nworkspace: ws\n"
        f"created_at: 2026-06-09T12:00:00\nelapsed_ms: 1\n"
        f"entities_used: []\nresponse_chars: 1\n---\n\n# Skill Run\n",
        encoding="utf-8",
    )
    (run_dir / "response.md").write_text("ok", encoding="utf-8")
    (artifacts / filename).write_bytes(b"docx-bytes")


@pytest.fixture()
def studio_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    from src.server.studio_routes import register_studio_ui_routes

    monkeypatch.setattr(get_settings(), "workspace", "ws-test")

    app = FastAPI()
    register_studio_ui_routes(
        app,
        workspace_dir=lambda: tmp_path,
        run_store_factory=SkillRunStore,
    )
    return TestClient(app)


def test_studio_list_route_reads_deliverables_via_run_store(
    studio_client: TestClient,
    tmp_path: Path,
) -> None:
    _seed_deliverable(
        tmp_path,
        skill="proposal-generator",
        run_id="20260609_120000_demo",
        filename="draft.docx",
    )

    response = studio_client.get("/api/ui/studio")

    assert response.status_code == 200
    body = response.json()
    assert body["workspace"] == "ws-test"
    assert body["count"] == 1
    assert body["deliverables"][0]["filename"] == "draft.docx"
    assert body["deliverables"][0]["skill"] == "proposal-generator"
