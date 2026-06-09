import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.entity_chunk_routes import load_entity_chunks, register_entity_chunk_routes


def test_load_entity_chunks_reads_name_variants_limits_and_shapes_previews(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    long_content = "x" * 605
    (workspace / "kv_store_entity_chunks.json").write_text(
        json.dumps({"Quoted Entity": {"chunk-1": {}, "chunk-2": {}, "chunk-3": {}}}),
        encoding="utf-8",
    )
    (workspace / "kv_store_text_chunks.json").write_text(
        json.dumps(
            {
                "chunk-1": {
                    "content": long_content,
                    "file_path": "source-a.pdf",
                    "chunk_order_index": 4,
                },
                "chunk-2": {"text": "short text", "full_doc_id": "source-b.pdf"},
                "chunk-3": {"content": "hidden by limit"},
            }
        ),
        encoding="utf-8",
    )

    payload = load_entity_chunks(workspace, '"Quoted Entity"', limit=2)

    assert payload["entity"] == '"Quoted Entity"'
    assert len(payload["chunks"]) == 2
    assert payload["chunks"][0] == {
        "chunk_id": "chunk-1",
        "file_path": "source-a.pdf",
        "chunk_order_index": 4,
        "snippet": long_content[:600] + "…",
    }
    assert payload["chunks"][1] == {
        "chunk_id": "chunk-2",
        "file_path": "source-b.pdf",
        "chunk_order_index": None,
        "snippet": "short text",
    }


def test_load_entity_chunks_returns_empty_for_missing_or_invalid_stores(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert load_entity_chunks(workspace, "missing") == {"entity": "missing", "chunks": []}

    (workspace / "kv_store_entity_chunks.json").write_text("not-json", encoding="utf-8")
    (workspace / "kv_store_text_chunks.json").write_text("{}", encoding="utf-8")

    assert load_entity_chunks(workspace, "bad") == {"entity": "bad", "chunks": []}


def test_entity_chunk_route_uses_workspace_dependency(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "kv_store_entity_chunks.json").write_text(
        json.dumps({"Entity": ["chunk-1"]}),
        encoding="utf-8",
    )
    (workspace / "kv_store_text_chunks.json").write_text(
        json.dumps({"chunk-1": {"content": "route content"}}),
        encoding="utf-8",
    )
    app = FastAPI()
    register_entity_chunk_routes(app, workspace_dir=lambda: workspace)
    client = TestClient(app)

    response = client.get("/api/ui/entity/Entity/chunks")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "entity": "Entity",
        "chunks": [
            {
                "chunk_id": "chunk-1",
                "file_path": None,
                "chunk_order_index": None,
                "snippet": "route content",
            }
        ],
    }
