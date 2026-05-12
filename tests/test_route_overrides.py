from types import SimpleNamespace

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