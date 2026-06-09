from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.graph_routes import json_safe, register_graph_routes


class _IsoFormatOnly:
    def iso_format(self) -> str:
        return "custom-date"


def test_json_safe_recursively_coerces_values() -> None:
    value = {
        "when": datetime(2025, 1, 2, 3, 4, 5),
        "items": (1, _IsoFormatOnly()),
        42: "numeric key",
    }

    assert json_safe(value) == {
        "when": "2025-01-02T03:04:05",
        "items": [1, "custom-date"],
        "42": "numeric key",
    }


def test_graph_route_returns_empty_payload_for_non_neo4j_backend(tmp_path) -> None:
    app = FastAPI()
    register_graph_routes(
        app,
        workspace_name=lambda: "empty",
        graph_storage=lambda: "NetworkXStorage",
        working_dir=lambda: tmp_path,
    )
    client = TestClient(app)

    response = client.get("/api/ui/graph?max_nodes=99999")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "backend": "networkxstorage",
        "workspace": "empty",
        "nodes": [],
        "edges": [],
        "total_nodes": 0,
        "returned_nodes": 0,
        "returned_edges": 0,
        "is_truncated": False,
    }