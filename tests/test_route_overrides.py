from types import SimpleNamespace
import asyncio

from src.server import routes
from src.server.routes import register_custom_ingestion_routes


class _FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message, *args):
        self.messages.append(message % args if args else message)


def test_register_custom_ingestion_routes_replaces_insert_and_upload() -> None:
    kept_route = SimpleNamespace(path="/query", methods={"GET"})
    removed_insert = SimpleNamespace(path="/insert", methods={"POST"})
    removed_upload = SimpleNamespace(path="/documents/upload", methods={"POST"})
    kept_get = SimpleNamespace(path="/insert", methods={"GET"})
    app = SimpleNamespace(router=SimpleNamespace(routes=[kept_route, removed_insert, removed_upload, kept_get]))
    rag_instance = object()
    logger = _FakeLogger()
    calls = []

    def create_insert(fake_app, fake_rag):
        calls.append(("insert", fake_app, fake_rag))

    def create_upload(fake_app, fake_rag):
        calls.append(("upload", fake_app, fake_rag))

    def create_scan(fake_app, fake_rag):
        calls.append(("scan", fake_app, fake_rag))

    register_custom_ingestion_routes(
        app,
        rag_instance,
        logger=logger,
        create_insert=create_insert,
        create_upload=create_upload,
        create_scan=create_scan,
    )

    assert app.router.routes == [kept_route, kept_get]
    assert calls == [
        ("insert", app, rag_instance),
        ("upload", app, rag_instance),
        ("scan", app, rag_instance),
    ]
    assert any("Custom endpoints registered" in message for message in logger.messages)


def test_route_document_processor_uses_native_lightrag_ingestion(monkeypatch) -> None:
    calls = []
    callback = object()

    async def fake_native_ingest(file_path, file_name, rag_instance, llm_func, *, callback):
        calls.append((file_path, file_name, rag_instance, llm_func, callback))
        return {"method": "native_lightrag_pipeline"}

    monkeypatch.setattr(routes, "run_native_ingestion", fake_native_ingest)
    monkeypatch.setattr(routes, "_callback", callback)
    rag = object()
    llm = object()

    result = asyncio.run(
        routes.process_document_with_native_ingestion(
            "inputs/ws/demo.pdf",
            "demo.pdf",
            rag,
            llm,
        )
    )

    assert result == {"method": "native_lightrag_pipeline"}
    assert calls == [("inputs/ws/demo.pdf", "demo.pdf", rag, llm, callback)]


def test_default_upload_and_scan_routes_share_native_processor(monkeypatch) -> None:
    processors = []

    def fake_register(app, rag, *, process_document_func, callback):
        processors.append(process_document_func)

    monkeypatch.setattr(routes, "register_insert_endpoint", fake_register)
    monkeypatch.setattr(routes, "register_documents_upload_endpoint", fake_register)
    monkeypatch.setattr(routes, "register_scan_endpoint", fake_register)

    app = object()
    rag = object()

    routes.create_insert_endpoint(app, rag)
    routes.create_documents_upload_endpoint(app, rag)
    routes.create_scan_endpoint(app, rag)

    assert processors == [routes.process_document_with_native_ingestion] * 3
