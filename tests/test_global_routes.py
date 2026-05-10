from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.global_store import GlobalStore
from src.server.global_routes import register_global_routes
from src.server.ui_routes import register_ui


def _note(body: str) -> str:
    return (
        "---\n"
        "date: 2026-05-09\n"
        "source: capture\n"
        "status: inbox\n"
        "tags: [meta, pricing]\n"
        "---\n\n"
        f"{body}\n"
    )


def _client(tmp_path: Path) -> tuple[TestClient, GlobalStore]:
    app = FastAPI()
    store = GlobalStore(root=tmp_path / "global")
    register_global_routes(
        app,
        store_factory=lambda: store,
        workspace_root=lambda: tmp_path / "rag_storage",
        today=lambda: "2026-05-09",
    )
    return TestClient(app), store


def test_global_bucket_routes_list_entries(tmp_path: Path) -> None:
    client, store = _client(tmp_path)
    store.write("inbox/2026-05-09-inbox.md", _note("Inbox note"))
    store.write("notes/2026-05-09-notes.md", _note("Notes note"))

    inbox = client.get("/api/global/inbox")
    notes = client.get("/api/global/notes")

    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["bucket"] == "inbox"
    assert inbox.json()["entries"][0]["path"] == "inbox/2026-05-09-inbox.md"

    assert notes.status_code == 200, notes.text
    assert notes.json()["bucket"] == "notes"
    assert notes.json()["entries"][0]["path"] == "notes/2026-05-09-notes.md"


def test_global_capture_route_writes_obsidian_note(tmp_path: Path) -> None:
    client, store = _client(tmp_path)

    response = client.post(
        "/api/global/capture",
        json={
            "content": "Remember this pricing signal",
            "slug": "pricing-signal",
            "tags": ["pricing", "meta"],
            "workspace": "afcap6_drfp_171",
            "wikilinks": ["[[price-to-win]]"],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["path"] == "inbox/2026-05-09-pricing-signal.md"

    written = store.read("inbox/2026-05-09-pricing-signal.md")
    assert "date: 2026-05-09" in written
    assert "workspace: afcap6_drfp_171" in written
    assert "tags: [pricing, meta]" in written
    assert "wikilinks: [[price-to-win]]" in written
    assert written.rstrip().endswith("Remember this pricing signal")


def test_global_promote_route_copies_note_into_workspace_sources(tmp_path: Path) -> None:
    client, store = _client(tmp_path)
    store.write("inbox/2026-05-09-promote.md", _note("Promote this note"))

    response = client.post(
        "/api/global/promote",
        json={
            "path": "inbox/2026-05-09-promote.md",
            "workspace": "afcap6_drfp_171",
        },
    )

    assert response.status_code == 200, response.text
    target = tmp_path / "rag_storage" / "afcap6_drfp_171" / "sources" / "2026-05-09-promote.md"
    assert response.json()["target"] == str(target)
    assert response.json()["target_relative"] == "sources/2026-05-09-promote.md"
    assert response.json()["ingestion_status"] == "pending"
    assert target.read_text(encoding="utf-8") == _note("Promote this note")


def test_global_promotions_route_lists_and_unpromotes_managed_source(tmp_path: Path) -> None:
    client, store = _client(tmp_path)
    store.write("notes/2026-05-09-promote.md", _note("Promote this note"))
    promoted = client.post(
        "/api/global/promote",
        json={
            "path": "notes/2026-05-09-promote.md",
            "workspace": "afcap6_drfp_171",
        },
    )
    assert promoted.status_code == 200, promoted.text

    listed = client.get(
        "/api/global/promotions",
        params={"workspace": "afcap6_drfp_171", "active_only": True},
    )

    assert listed.status_code == 200, listed.text
    assert listed.json()["promotions"][0]["source"] == "notes/2026-05-09-promote.md"
    assert listed.json()["promotions"][0]["active"] is True

    removed = client.request(
        "DELETE",
        "/api/global/promote",
        json={
            "path": "notes/2026-05-09-promote.md",
            "workspace": "afcap6_drfp_171",
        },
    )

    assert removed.status_code == 200, removed.text
    assert removed.json()["deleted_target"] is True
    assert not Path(promoted.json()["target"]).exists()


def test_global_routes_reject_invalid_bucket_and_workspace(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    bad_bucket = client.post(
        "/api/global/capture",
        json={
            "content": "bad",
            "bucket": "../bad",
            "tags": ["meta", "ui"],
        },
    )
    bad_workspace = client.post(
        "/api/global/promote",
        json={
            "path": "inbox/demo.md",
            "workspace": "../bad",
        },
    )

    assert bad_bucket.status_code == 400
    assert bad_workspace.status_code == 400


async def _stub_query(_text: str, _mode: str, _history: list[dict], _stream: bool, _overrides: dict):
    return "ok"


def test_register_ui_mounts_global_routes() -> None:
    app = FastAPI()

    register_ui(app, query_func=_stub_query)

    paths = {route.path for route in app.routes}
    assert "/api/global/inbox" in paths
    assert "/api/global/capture" in paths
    assert "/api/global/promote" in paths
    assert "/api/global/promotions" in paths