from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.chat_routes import register_chat_routes, trim_sources
from src.server.chat_store import ChatStore


class _QuerySettings:
    def build_overrides(self) -> dict[str, Any]:
        return {"top_k": 7}


def _client(tmp_path, *, query_func=None, data_func=None) -> tuple[TestClient, list[tuple[Any, ...]]]:
    calls: list[tuple[Any, ...]] = []

    async def default_query_func(text, mode, history, stream, overrides):
        calls.append((text, mode, history, stream, overrides))
        return "assistant <think>hidden</think>answer"

    app = FastAPI()
    store = ChatStore(
        workspace_dir=lambda: tmp_path,
        now=lambda: "now",
        history_pairs=lambda: 5,
    )
    register_chat_routes(
        app,
        chat_store=store,
        query_settings=_QuerySettings(),
        query_func=query_func or default_query_func,
        data_func=data_func,
        now=lambda: "now",
    )
    return TestClient(app), calls


def test_trim_sources_compacts_retrieval_payload() -> None:
    long_content = "x" * 805
    result = trim_sources(
        {
            "chunks": [
                {
                    "reference_id": 12,
                    "chunk_id": "c1",
                    "file_path": "doc.pdf",
                    "content": long_content,
                },
                "skip",
            ],
            "references": [{"reference_id": "r1", "file_path": "doc.pdf"}],
            "entities": [{}, {}],
            "relationships": [{}],
        }
    )

    assert result["counts"] == {
        "chunks": 1,
        "entities": 2,
        "relationships": 1,
        "references": 1,
    }
    assert result["chunks"][0]["preview"].endswith("…")
    assert result["chunks"][0]["char_count"] == 805
    assert result["chunks"][0]["truncated"] is True


def test_chat_crud_and_sync_message_routes(tmp_path) -> None:
    client, calls = _client(tmp_path)

    created = client.post(
        "/api/ui/chats",
        json={"title": "New chat", "mode": "mix", "rfp_context": "ctx"},
    )
    assert created.status_code == 201, created.text
    chat_id = created.json()["id"]

    listed = client.get("/api/ui/chats")
    assert listed.status_code == 200, listed.text
    assert listed.json()["chats"][0]["id"] == chat_id

    updated = client.patch(
        f"/api/ui/chats/{chat_id}",
        json={"title": "Renamed", "mode": "hybrid"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "Renamed"
    assert updated.json()["mode"] == "hybrid"

    message = client.post(
        f"/api/ui/chats/{chat_id}/messages",
        json={"content": "What matters?"},
    )
    assert message.status_code == 200, message.text
    assert message.json()["assistant"]["content"] == "assistant answer"
    assert calls[0] == ("What matters?", "hybrid", [], False, {"top_k": 7})

    full = client.get(f"/api/ui/chats/{chat_id}")
    assert full.status_code == 200, full.text
    assert [item["role"] for item in full.json()["messages"]] == ["user", "assistant"]

    deleted = client.delete(f"/api/ui/chats/{chat_id}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"status": "deleted", "id": chat_id}


def test_streaming_message_route_emits_sse_and_persists_sources(tmp_path) -> None:
    query_calls: list[tuple[Any, ...]] = []
    data_calls: list[tuple[Any, ...]] = []

    async def query_func(text, mode, history, stream, overrides):
        query_calls.append((text, mode, history, stream, overrides))

        async def chunks() -> AsyncIterator[str]:
            yield "stream "
            yield "answer"

        return chunks()

    async def data_func(text, mode, history, overrides):
        data_calls.append((text, mode, history, overrides))
        return {
            "status": "success",
            "data": {
                "chunks": [
                    {
                        "reference_id": "r1",
                        "chunk_id": "c1",
                        "file_path": "doc.pdf",
                        "content": "source text",
                    }
                ],
                "references": [{"reference_id": "r1", "file_path": "doc.pdf"}],
                "entities": [{}],
                "relationships": [{}, {}],
            },
        }

    client, _ = _client(tmp_path, query_func=query_func, data_func=data_func)
    created = client.post("/api/ui/chats", json={"title": "Stream", "mode": "mix"})
    chat_id = created.json()["id"]

    response = client.post(
        f"/api/ui/chats/{chat_id}/messages/stream",
        json={"content": "Stream it"},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: open" in response.text
    assert "event: sources" in response.text
    assert "event: token" in response.text
    assert "stream answer" in response.text
    assert "event: done" in response.text
    assert query_calls[0] == ("Stream it", "mix", [], True, {"top_k": 7})
    assert data_calls[0] == ("Stream it", "mix", [], {"top_k": 7})

    full = client.get(f"/api/ui/chats/{chat_id}").json()
    assert [item["role"] for item in full["messages"]] == ["user", "assistant"]
    assistant = full["messages"][1]
    assert assistant["content"] == "stream answer"
    assert assistant["sources"]["counts"] == {
        "chunks": 1,
        "entities": 1,
        "relationships": 2,
        "references": 1,
    }
    assert assistant["timing"]["chunk_count"] == 2
