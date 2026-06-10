from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server import chat_routes
from src.server.chat_routes import register_chat_routes, trim_sources
from src.server.chat_store import ChatStore
from src.server.handoff_compose import HandoffComposeResult


class _QuerySettings:
    def build_overrides(self) -> dict[str, Any]:
        return {"top_k": 7}


class _Settings:
    ollama_model = "qwen3.5:9b"


def _client(
    tmp_path,
    *,
    query_func=None,
    query_llm_func=None,
    settings_provider=None,
) -> tuple[TestClient, list[tuple[Any, ...]]]:
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
        query_llm_func=query_llm_func,
        now=lambda: "now",
        settings_provider=settings_provider or (lambda: _Settings()),
    )
    return TestClient(app), calls


def _native_sources_llm_result(*, stream: bool, answer: str | AsyncIterator[str]):
    if stream:

        async def chunks() -> AsyncIterator[str]:
            if hasattr(answer, "__aiter__"):
                async for item in answer:
                    yield item
            else:
                yield str(answer)

        llm_response = {
            "content": None,
            "response_iterator": chunks(),
            "is_streaming": True,
        }
    else:
        llm_response = {
            "content": answer,
            "response_iterator": None,
            "is_streaming": False,
        }

    return {
        "status": "success",
        "data": {
            "chunks": [
                {
                    "reference_id": "ref-native-1",
                    "chunk_id": "chunk-native-1",
                    "file_path": "native-rfp.pdf",
                    "content": "Native-ingested PWS source text",
                }
            ],
            "references": [
                {"reference_id": "ref-native-1", "file_path": "native-rfp.pdf"}
            ],
            "entities": [{"entity_name": "Workload Requirement"}],
            "relationships": [{"src_id": "Workload Requirement"}],
        },
        "llm_response": llm_response,
    }


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


def test_sync_message_route_persists_native_sources(tmp_path) -> None:
    query_llm_calls: list[tuple[Any, ...]] = []

    async def query_llm_func(text, mode, history, stream, overrides):
        query_llm_calls.append((text, mode, history, stream, overrides))
        return _native_sources_llm_result(
            stream=False,
            answer="Native answer cites workload requirement.",
        )

    client, _ = _client(tmp_path, query_llm_func=query_llm_func)
    created = client.post("/api/ui/chats", json={"title": "Native", "mode": "mix"})
    chat_id = created.json()["id"]

    response = client.post(
        f"/api/ui/chats/{chat_id}/messages",
        json={"content": "What workload drives pricing?"},
    )

    assert response.status_code == 200, response.text
    assistant = response.json()["assistant"]
    assert assistant["content"] == "Native answer cites workload requirement."
    assert assistant["sources"]["counts"] == {
        "chunks": 1,
        "entities": 1,
        "relationships": 1,
        "references": 1,
    }
    assert assistant["sources"]["chunks"][0]["file_path"] == "native-rfp.pdf"
    assert query_llm_calls == [
        ("What workload drives pricing?", "mix", [], False, {"top_k": 7}),
    ]


def test_streaming_message_route_emits_sse_and_persists_sources(tmp_path) -> None:
    query_llm_calls: list[tuple[Any, ...]] = []

    async def stream_answer():
        yield "stream "
        yield "answer"

    async def query_llm_func(text, mode, history, stream, overrides):
        query_llm_calls.append((text, mode, history, stream, overrides))
        return _native_sources_llm_result(stream=True, answer=stream_answer())

    client, _ = _client(tmp_path, query_llm_func=query_llm_func)
    created = client.post("/api/ui/chats", json={"title": "Stream", "mode": "mix"})
    chat_id = created.json()["id"]

    response = client.post(
        f"/api/ui/chats/{chat_id}/messages/stream",
        json={"content": "Stream it"},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: open" in response.text
    assert "source_counts" in response.text
    assert "event: token" in response.text
    assert "event: done" in response.text
    assert "event: sources" not in response.text
    assert query_llm_calls == [("Stream it", "mix", [], True, {"top_k": 7})]

    full = client.get(f"/api/ui/chats/{chat_id}").json()
    assert [item["role"] for item in full["messages"]] == ["user", "assistant"]
    assistant = full["messages"][1]
    assert assistant["content"] == "stream answer"
    assert assistant["sources"]["counts"] == {
        "chunks": 1,
        "entities": 1,
        "relationships": 1,
        "references": 1,
    }
    assert assistant["timing"]["chunk_count"] == 2


def test_streaming_message_route_uses_single_query_llm_pass(tmp_path) -> None:
    query_calls: list[tuple[Any, ...]] = []
    query_llm_calls: list[tuple[Any, ...]] = []

    async def query_func(text, mode, history, stream, overrides):
        query_calls.append((text, mode, history, stream, overrides))
        return "should-not-run"

    async def chunks() -> AsyncIterator[str]:
        yield "single "
        yield "pass"

    async def query_llm_func(text, mode, history, stream, overrides):
        query_llm_calls.append((text, mode, history, stream, overrides))
        return {
            "status": "success",
            "data": {
                "chunks": [
                    {
                        "reference_id": "r9",
                        "chunk_id": "c9",
                        "file_path": "one-pass.pdf",
                        "content": "retrieved once",
                    }
                ],
                "references": [{"reference_id": "r9", "file_path": "one-pass.pdf"}],
                "entities": [{}],
                "relationships": [],
            },
            "llm_response": {
                "content": None,
                "response_iterator": chunks(),
                "is_streaming": True,
            },
        }

    client, _ = _client(
        tmp_path,
        query_func=query_func,
        query_llm_func=query_llm_func,
    )
    created = client.post("/api/ui/chats", json={"title": "Single pass", "mode": "mix"})
    chat_id = created.json()["id"]

    response = client.post(
        f"/api/ui/chats/{chat_id}/messages/stream",
        json={"content": "One retrieval only"},
    )

    assert response.status_code == 200, response.text
    assert "event: token" in response.text
    assert "source_counts" in response.text
    assert query_llm_calls == [("One retrieval only", "mix", [], True, {"top_k": 7})]
    assert query_calls == []

    assistant = client.get(f"/api/ui/chats/{chat_id}").json()["messages"][1]
    assert assistant["content"] == "single pass"
    assert assistant["sources"]["chunks"][0]["file_path"] == "one-pass.pdf"


def test_stream_message_accepts_per_message_bypass_override(tmp_path) -> None:
    query_llm_calls: list[tuple[Any, ...]] = []

    async def query_llm_func(text, mode, history, stream, overrides):
        query_llm_calls.append((text, mode, history, stream, overrides))
        return _native_sources_llm_result(stream=False, answer="external synthesis")

    client, _ = _client(tmp_path, query_llm_func=query_llm_func)
    created = client.post("/api/ui/chats", json={"title": "Bypass once", "mode": "mix"})
    chat_id = created.json()["id"]

    response = client.post(
        f"/api/ui/chats/{chat_id}/messages/stream",
        json={"content": "Research incumbent tax posture", "mode": "bypass"},
    )

    assert response.status_code == 200, response.text
    assert "Bypass" in response.text or "bypass" in response.text
    assert query_llm_calls == [
        ("Research incumbent tax posture", "bypass", [], True, {"top_k": 7}),
    ]

    full = client.get(f"/api/ui/chats/{chat_id}").json()
    assert full["mode"] == "mix"
    user = full["messages"][0]
    assistant = full["messages"][1]
    assert user["mode"] == "bypass"
    assert user["mode_override"] is True
    assert assistant["mode"] == "bypass"


def test_create_chat_persists_handoff_metadata(tmp_path) -> None:
    client, _ = _client(tmp_path)
    source = client.post("/api/ui/chats", json={"title": "Source", "mode": "mix"})
    source_id = source.json()["id"]

    created = client.post(
        "/api/ui/chats",
        json={
            "title": "NET 30 cash-flow risk",
            "mode": "hybrid",
            "rfp_context": "MCPP",
            "handoff_from": {
                "chat_id": source_id,
                "message_index": 3,
                "excerpt": "NET 30 vs receivables is Critical",
            },
        },
    )
    assert created.status_code == 201, created.text
    branch_id = created.json()["id"]
    assert created.json()["handoff_from"] == {
        "chat_id": source_id,
        "message_index": 3,
        "excerpt": "NET 30 vs receivables is Critical",
    }

    full = client.get(f"/api/ui/chats/{branch_id}")
    assert full.status_code == 200, full.text
    assert full.json()["handoff_from"]["chat_id"] == source_id
    assert full.json()["mode"] == "hybrid"
    assert full.json()["rfp_context"] == "MCPP"


def test_handoff_compose_returns_packed_seed(monkeypatch, tmp_path) -> None:
    client, _ = _client(tmp_path)
    source = client.post("/api/ui/chats", json={"title": "Source", "mode": "mix"})
    source_id = source.json()["id"]
    full = client.get(f"/api/ui/chats/{source_id}").json()
    client.post(
        f"/api/ui/chats/{source_id}/messages",
        json={"content": "What is NET 30 risk?"},
    )
    full = client.get(f"/api/ui/chats/{source_id}").json()
    assistant_index = len(full["messages"]) - 1

    async def fake_compose(payload, *, settings):
        return HandoffComposeResult(
            title="NET 30 cash risk",
            focus_summary="Payment terms vs receivables",
            claims_to_ground=["NET 30 clause exists"],
            seed_prompt="Packed seed for grounded branch",
            composed=True,
            model="qwen3.5:9b",
        )

    monkeypatch.setattr(chat_routes, "compose_insight_handoff", fake_compose)

    response = client.post(
        "/api/ui/chats/handoff/compose",
        json={
            "source_chat_id": source_id,
            "message_index": assistant_index,
            "quote": "NET 30 payment terms create cash-flow risk",
            "framing_question": "Walk me through evidence",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["composed"] is True
    assert body["seed_prompt"] == "Packed seed for grounded branch"
    assert body["title"] == "NET 30 cash risk"


def test_handoff_compose_503_when_ollama_unavailable(monkeypatch, tmp_path) -> None:
    client, _ = _client(tmp_path)
    source = client.post("/api/ui/chats", json={"title": "Source", "mode": "mix"})
    source_id = source.json()["id"]
    client.post(
        f"/api/ui/chats/{source_id}/messages",
        json={"content": "Question"},
    )
    full = client.get(f"/api/ui/chats/{source_id}").json()
    assistant_index = len(full["messages"]) - 1

    async def unavailable(payload, *, settings):
        raise RuntimeError("Ollama is not reachable")

    monkeypatch.setattr(chat_routes, "compose_insight_handoff", unavailable)

    response = client.post(
        "/api/ui/chats/handoff/compose",
        json={
            "source_chat_id": source_id,
            "message_index": assistant_index,
            "quote": "Some insight",
        },
    )
    assert response.status_code == 503, response.text


def test_message_mode_override_rejects_invalid_mode(tmp_path) -> None:
    client, _ = _client(tmp_path)
    created = client.post("/api/ui/chats", json={"title": "Bad mode", "mode": "mix"})
    chat_id = created.json()["id"]

    response = client.post(
        f"/api/ui/chats/{chat_id}/messages/stream",
        json={"content": "Hello", "mode": "not-a-mode"},
    )

    assert response.status_code == 400, response.text