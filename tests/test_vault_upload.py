"""#139 — vault-only upload: skip KG extraction, create vault note instead."""
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server import upload_routes
from src.server.vault_store import VaultStore

_NOW = lambda: "2026-01-01T00:00:00"


class _Callback:
    async def register_request_start(self, name: str): ...
    async def register_request_end(self, name: str): ...


class _Rag:
    def __init__(self):
        self.llm_model_func = object()


def _make_app(tmp_path: Path, monkeypatch, *, process_calls: dict | None = None):
    """Return (TestClient, VaultStore) wired with vault_only support."""
    app = FastAPI()
    rag = _Rag()
    callback = _Callback()
    saved_path = tmp_path / "report.pdf"
    saved_path.write_bytes(b"PDF content about capabilities")
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    store = VaultStore(vault_dir=vault_dir, now=_NOW)

    if process_calls is not None:
        async def fake_process(fp, fn, ri, lf):
            process_calls["count"] = process_calls.get("count", 0) + 1
            return {"relationships_inferred": 1}
        process_doc = fake_process
    else:
        async def noop_process(fp, fn, ri, lf):
            return {"relationships_inferred": 0}
        process_doc = noop_process

    async def fake_save(file, workspace):
        return saved_path

    monkeypatch.setattr(upload_routes, "save_upload_to_workspace", fake_save)

    upload_routes.create_documents_upload_endpoint(
        app, rag,
        process_document_func=process_doc,
        callback=callback,
        vault_store=store,
    )
    return TestClient(app), store


# ---------------------------------------------------------------------------
# Tracer bullet: vault_only=true creates a vault note, skips KG
# ---------------------------------------------------------------------------

def test_vault_only_creates_note_and_returns_vault_status(monkeypatch, tmp_path: Path):
    """POST /documents/upload?vault_only=true → note in vault, status='vault'."""
    calls = {}
    client, store = _make_app(tmp_path, monkeypatch, process_calls=calls)

    resp = client.post(
        "/documents/upload?vault_only=true",
        files={"file": ("report.pdf", BytesIO(b"PDF content about capabilities"), "application/pdf")},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "vault"
    assert "vault_note_id" in data
    # KG extraction must NOT have run
    assert calls.get("count", 0) == 0


# ---------------------------------------------------------------------------
# pursuit wired to workspace param
# ---------------------------------------------------------------------------

def test_vault_only_with_workspace_sets_pursuit(monkeypatch, tmp_path: Path):
    """vault_only=true + workspace=foo → note.pursuit == 'foo'."""
    client, store = _make_app(tmp_path, monkeypatch)

    resp = client.post(
        "/documents/upload?vault_only=true&workspace=foo",
        files={"file": ("report.pdf", BytesIO(b"content"), "application/pdf")},
    )

    assert resp.status_code == 200, resp.text
    note_id = resp.json()["vault_note_id"]
    note = store.read(note_id)
    assert note.get("pursuit") == "foo"


def test_vault_only_without_workspace_omits_pursuit(monkeypatch, tmp_path: Path):
    """vault_only=true, no workspace → pursuit field absent from note."""
    client, store = _make_app(tmp_path, monkeypatch)

    resp = client.post(
        "/documents/upload?vault_only=true",
        files={"file": ("report.pdf", BytesIO(b"content"), "application/pdf")},
    )

    assert resp.status_code == 200, resp.text
    note_id = resp.json()["vault_note_id"]
    note = store.read(note_id)
    assert not note.get("pursuit")


# ---------------------------------------------------------------------------
# vault_only=false (default) — existing KG path untouched
# ---------------------------------------------------------------------------

def test_vault_only_false_runs_kg_extraction(monkeypatch, tmp_path: Path):
    """vault_only absent/false → normal KG processing, no vault_note_id."""
    calls = {}
    client, store = _make_app(tmp_path, monkeypatch, process_calls=calls)

    resp = client.post(
        "/documents/upload",
        files={"file": ("report.pdf", BytesIO(b"PDF content"), "application/pdf")},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "success"
    assert "vault_note_id" not in data
    assert calls.get("count", 0) == 1
