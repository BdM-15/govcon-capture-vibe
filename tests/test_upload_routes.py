from io import BytesIO
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server import upload_routes


class _Callback:
    def __init__(self):
        self.started: list[str] = []
        self.ended: list[str] = []

    async def register_request_start(self, name: str):
        self.started.append(name)

    async def register_request_end(self, name: str):
        self.ended.append(name)


class _Rag:
    def __init__(self):
        self.llm_model_func = object()


def test_insert_endpoint_processes_saved_file(monkeypatch, tmp_path: Path) -> None:
    app = FastAPI()
    rag = _Rag()
    callback = _Callback()
    saved_path = tmp_path / "demo.pdf"

    async def fake_save(file, workspace):
        return saved_path

    async def fake_process(file_path, file_name, rag_instance, llm_func):
        return {"relationships_inferred": 3, "method": "native_lightrag_pipeline"}

    monkeypatch.setattr(upload_routes, "save_upload_to_workspace", fake_save)

    upload_routes.create_insert_endpoint(
        app,
        rag,
        process_document_func=fake_process,
        callback=callback,
    )
    client = TestClient(app)

    response = client.post(
        "/insert",
        files={"file": ("demo.pdf", BytesIO(b"pdf"), "application/pdf")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["relationships_inferred"] == 3
    assert response.json()["method"] == "native_lightrag_pipeline"
    assert callback.started == ["demo.pdf"]
    assert callback.ended == ["demo.pdf"]


def test_documents_upload_stage_only_skips_processing(monkeypatch, tmp_path: Path) -> None:
    app = FastAPI()
    rag = _Rag()
    callback = _Callback()
    saved_path = tmp_path / "demo.pdf"
    called = {"process": 0}

    async def fake_save(file, workspace):
        return saved_path

    async def fake_process(file_path, file_name, rag_instance, llm_func):
        called["process"] += 1
        return {"relationships_inferred": 0}

    monkeypatch.setattr(upload_routes, "save_upload_to_workspace", fake_save)

    upload_routes.create_documents_upload_endpoint(
        app,
        rag,
        process_document_func=fake_process,
        callback=callback,
    )
    client = TestClient(app)

    response = client.post(
        "/documents/upload?stage_only=true",
        files={"file": ("demo.pdf", BytesIO(b"pdf"), "application/pdf")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "staged"
    assert called["process"] == 0
    assert callback.started == []
    assert callback.ended == []


def test_documents_upload_processes_when_not_stage_only(monkeypatch, tmp_path: Path) -> None:
    app = FastAPI()
    rag = _Rag()
    callback = _Callback()
    saved_path = tmp_path / "demo.pdf"

    async def fake_save(file, workspace):
        return saved_path

    async def fake_process(file_path, file_name, rag_instance, llm_func):
        return {"relationships_inferred": 1, "method": "native_lightrag_pipeline"}

    monkeypatch.setattr(upload_routes, "save_upload_to_workspace", fake_save)

    upload_routes.create_documents_upload_endpoint(
        app,
        rag,
        process_document_func=fake_process,
        callback=callback,
    )
    client = TestClient(app)

    response = client.post(
        "/documents/upload",
        files={"file": ("demo.pdf", BytesIO(b"pdf"), "application/pdf")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success"
    assert response.json()["relationships_inferred"] == 1
    assert response.json()["method"] == "native_lightrag_pipeline"
    assert callback.started == ["demo.pdf"]
    assert callback.ended == ["demo.pdf"]
