"""#140 — Evergreen bootstrap: co-process evergreen docs on first workspace upload."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _DocStatus:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    async def get_docs_paginated(self, limit=20, **kwargs):
        # Returns (([(id, data)], total_count),)  — mirrors LightRAG compat shim
        pairs = [(str(i), d) for i, d in enumerate(self._docs)]
        return (pairs, len(self._docs)),


class _LightRAG:
    def __init__(self, docs=None):
        self.doc_status = _DocStatus(docs or [])


class _Rag:
    def __init__(self, docs=None):
        self.lightrag = _LightRAG(docs)
        self.llm_model_func = object()


class _Callback:
    async def register_request_start(self, name): ...
    async def register_request_end(self, name): ...


# ---------------------------------------------------------------------------
# list_evergreen_files
# ---------------------------------------------------------------------------

def test_list_evergreen_files_returns_md_files(tmp_path):
    from src.server.evergreen_bootstrap import list_evergreen_files

    ev = tmp_path / "evergreen"
    ev.mkdir()
    (ev / "capabilities.md").write_text("cap content")
    (ev / "past_perf.md").write_text("pp content")
    (ev / "ignored.pdf").write_text("binary")

    result = list_evergreen_files(ev)
    names = {p.name for p in result}
    assert names == {"capabilities.md", "past_perf.md"}


def test_list_evergreen_files_empty_dir(tmp_path):
    from src.server.evergreen_bootstrap import list_evergreen_files

    ev = tmp_path / "evergreen"
    ev.mkdir()
    assert list_evergreen_files(ev) == []


def test_list_evergreen_files_missing_dir(tmp_path):
    from src.server.evergreen_bootstrap import list_evergreen_files

    result = list_evergreen_files(tmp_path / "does_not_exist")
    assert result == []


# ---------------------------------------------------------------------------
# is_new_workspace
# ---------------------------------------------------------------------------

def test_is_new_workspace_true_when_no_docs():
    from src.server.evergreen_bootstrap import is_new_workspace

    rag = _Rag(docs=[])
    assert asyncio.run(is_new_workspace(rag)) is True


def test_is_new_workspace_false_when_docs_exist():
    from src.server.evergreen_bootstrap import is_new_workspace

    rag = _Rag(docs=[{"status": "processed", "file_name": "rfp.pdf"}])
    assert asyncio.run(is_new_workspace(rag)) is False


# ---------------------------------------------------------------------------
# seed_evergreen_docs
# ---------------------------------------------------------------------------

def test_seed_evergreen_docs_processes_all_files(tmp_path):
    from src.server.evergreen_bootstrap import seed_evergreen_docs

    ev = tmp_path / "evergreen"
    ev.mkdir()
    (ev / "capabilities.md").write_text("cap")
    (ev / "past_perf.md").write_text("pp")

    calls = []

    async def fake_process(fp, fn, ri, lf):
        calls.append(fn)
        return {"relationships_inferred": 1}

    rag = _Rag()
    count = asyncio.run(
        seed_evergreen_docs(rag, ev, fake_process, _Callback(), workspace="acme-rfp")
    )

    assert count == 2
    assert set(calls) == {"capabilities.md", "past_perf.md"}


def test_seed_evergreen_docs_returns_zero_for_empty_dir(tmp_path):
    from src.server.evergreen_bootstrap import seed_evergreen_docs

    ev = tmp_path / "empty_evergreen"
    ev.mkdir()

    async def should_not_run(*args):
        raise AssertionError("should not be called")

    rag = _Rag()
    count = asyncio.run(
        seed_evergreen_docs(rag, ev, should_not_run, _Callback(), workspace="ws")
    )
    assert count == 0


def test_seed_evergreen_docs_missing_dir_is_noop(tmp_path):
    from src.server.evergreen_bootstrap import seed_evergreen_docs

    async def should_not_run(*args):
        raise AssertionError("should not be called")

    rag = _Rag()
    count = asyncio.run(
        seed_evergreen_docs(rag, tmp_path / "missing", should_not_run, _Callback(), workspace="ws")
    )
    assert count == 0


# ---------------------------------------------------------------------------
# Upload-route integration: evergreen seeded on first upload, not on subsequent
# ---------------------------------------------------------------------------

def _make_upload_app(tmp_path: Path, monkeypatch, *, docs_in_status=None, ev_files=None):
    """Return (TestClient, process_calls list, evergreen_dir)."""
    from io import BytesIO
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.server import upload_routes

    app = FastAPI()

    class _DocStatus:
        def __init__(self, docs):
            self._docs = docs
        async def get_docs_paginated(self, limit=20, **kwargs):
            pairs = [(str(i), d) for i, d in enumerate(self._docs)]
            return (pairs, len(self._docs)),

    class _LightRAG:
        def __init__(self, docs):
            self.doc_status = _DocStatus(docs)

    class _Rag:
        def __init__(self, docs):
            self.lightrag = _LightRAG(docs)
            self.llm_model_func = object()

    rag = _Rag(docs_in_status or [])

    class _CB:
        async def register_request_start(self, n): ...
        async def register_request_end(self, n): ...

    calls = []

    async def fake_process(fp, fn, ri, lf):
        calls.append(fn)
        return {"relationships_inferred": 0}

    async def fake_save(file, workspace):
        saved = tmp_path / file.filename
        saved.write_bytes(b"content")
        return saved

    monkeypatch.setattr(upload_routes, "save_upload_to_workspace", fake_save)

    # Create evergreen dir with optional files
    ev_dir = tmp_path / "evergreen"
    ev_dir.mkdir()
    for name in (ev_files or []):
        (ev_dir / name).write_text(f"content of {name}")

    upload_routes.create_documents_upload_endpoint(
        app, rag,
        process_document_func=fake_process,
        callback=_CB(),
        evergreen_dir=ev_dir,
    )
    return TestClient(app), calls, ev_dir


def test_first_upload_seeds_evergreen(monkeypatch, tmp_path: Path):
    """New workspace (0 docs) + evergreen files → evergreen co-processed after main doc."""
    from io import BytesIO
    client, calls, _ = _make_upload_app(
        tmp_path, monkeypatch,
        docs_in_status=[],
        ev_files=["capabilities.md", "past_perf.md"],
    )

    resp = client.post(
        "/documents/upload",
        files={"file": ("rfp.pdf", BytesIO(b"rfp"), "application/pdf")},
    )

    assert resp.status_code == 200
    # main doc + 2 evergreen = 3 total calls
    assert "rfp.pdf" in calls
    assert "capabilities.md" in calls
    assert "past_perf.md" in calls


def test_existing_workspace_skips_evergreen(monkeypatch, tmp_path: Path):
    """Existing workspace (has docs) → evergreen NOT re-processed."""
    from io import BytesIO
    client, calls, _ = _make_upload_app(
        tmp_path, monkeypatch,
        docs_in_status=[{"status": "processed", "file_name": "old.pdf"}],
        ev_files=["capabilities.md"],
    )

    resp = client.post(
        "/documents/upload",
        files={"file": ("rfp2.pdf", BytesIO(b"rfp2"), "application/pdf")},
    )

    assert resp.status_code == 200
    assert "rfp2.pdf" in calls
    assert "capabilities.md" not in calls
