from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server import scan_routes


class _DocStatus:
    def __init__(self, statuses: dict[str, dict]):
        self._statuses = statuses

    async def get_doc_by_file_path(self, name: str):
        return self._statuses.get(name)


class _LightRAG:
    def __init__(self, statuses: dict[str, dict]):
        self.doc_status = _DocStatus(statuses)


class _Rag:
    def __init__(self, statuses: dict[str, dict] | None = None):
        self.lightrag = _LightRAG(statuses or {})
        self.llm_model_func = object()


class _Callback:
    def __init__(self):
        self.started: list[str] = []
        self.ended: list[str] = []

    async def register_request_start(self, name: str):
        self.started.append(name)

    async def register_request_end(self, name: str):
        self.ended.append(name)


def test_filter_already_processed_splits_processed_and_pending(tmp_path: Path) -> None:
    rag = _Rag({"done.pdf": {"status": "processed"}})
    files = [tmp_path / "done.pdf", tmp_path / "new.pdf"]

    to_process, already = __import__("asyncio").run(scan_routes.filter_already_processed(rag, files))

    assert [path.name for path in to_process] == ["new.pdf"]
    assert already == ["done.pdf"]


def test_scan_endpoint_returns_empty_when_no_files(tmp_path: Path, monkeypatch) -> None:
    app = FastAPI()
    rag = _Rag()
    callback = _Callback()

    monkeypatch.setattr(scan_routes, "resolve_scan_folder", lambda workspace: tmp_path)
    monkeypatch.setattr(scan_routes, "list_scannable_files", lambda folder: [])

    scan_routes.create_scan_endpoint(
        app,
        rag,
        process_document_func=None,
        callback=callback,
    )
    client = TestClient(app)

    response = client.post("/scan-rfp")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "empty"
    assert payload["files_found"] == 0


def test_scan_endpoint_starts_background_scan(tmp_path: Path, monkeypatch) -> None:
    app = FastAPI()
    rag = _Rag()
    callback = _Callback()
    seen: list[tuple[Path, str]] = []
    files = [tmp_path / "a.pdf"]

    async def fake_run_scan(rag_instance, folder, track_id, *, process_document_func, callback):
        seen.append((folder, track_id))

    monkeypatch.setattr(scan_routes, "resolve_scan_folder", lambda workspace: tmp_path)
    monkeypatch.setattr(scan_routes, "list_scannable_files", lambda folder: files)
    monkeypatch.setattr(scan_routes, "run_scan", fake_run_scan)

    scan_routes.create_scan_endpoint(
        app,
        rag,
        process_document_func=object(),
        callback=callback,
    )
    client = TestClient(app)

    response = client.post("/scan-rfp")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "scanning_started"
    assert payload["files_found"] == 1
    assert seen and seen[0][0] == tmp_path
    assert seen[0][1].startswith("scan-")