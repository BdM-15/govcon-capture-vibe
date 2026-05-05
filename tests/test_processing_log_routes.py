from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.document_routes import register_processing_log_routes


def test_processing_log_snapshot_route_uses_injected_reader() -> None:
    app = FastAPI()

    def read_log_snapshot(*, limit: int) -> dict[str, Any]:
        return {"limit": limit, "events": [{"message": "ready"}]}

    register_processing_log_routes(app, read_log_snapshot=read_log_snapshot)
    client = TestClient(app)

    response = client.get("/api/ui/processing-log?limit=12")

    assert response.status_code == 200, response.text
    assert response.json() == {"limit": 12, "events": [{"message": "ready"}]}


def test_processing_log_stream_route_formats_sse_events() -> None:
    app = FastAPI()

    async def stream_log_events(*, initial_limit: int) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "snapshot", "events": [{"limit": initial_limit}], "path": "demo.log"}
        yield {"type": "event", "event": {"message": "new"}}
        yield {"type": "ping"}

    register_processing_log_routes(app, stream_log_events=stream_log_events)
    client = TestClient(app)

    response = client.get("/api/ui/processing-log/stream?limit=3")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: open" in response.text
    assert 'event: snapshot\ndata: {"events": [{"limit": 3}], "path": "demo.log"}' in response.text
    assert 'event: event\ndata: {"message": "new"}' in response.text
    assert ": ping" in response.text
