from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.workspace_routes import json_safe, load_graph_networkx, register_graph_routes


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


def test_load_graph_networkx_reads_filters_and_shapes_payload(tmp_path) -> None:
    import networkx as nx

    workspace_dir = tmp_path / "demo"
    workspace_dir.mkdir()
    graph = nx.Graph()
    graph.add_node("r1", entity_id="REQ-1", entity_type="requirement")
    graph.add_node("d1", entity_id="DEL-1", entity_type="deliverable")
    graph.add_edge("r1", "d1", relationship_type="SATISFIED_BY", score="1")
    nx.write_graphml(graph, workspace_dir / "graph_chunk_entity_relation.graphml")

    payload = load_graph_networkx("demo", 10, "requirement", working_dir=tmp_path)

    assert payload["backend"] == "networkx"
    assert payload["workspace"] == "demo"
    assert payload["total_nodes"] == 1
    assert payload["returned_nodes"] == 1
    assert payload["returned_edges"] == 0
    assert payload["nodes"][0]["labels"] == ["REQ-1"]
    assert payload["nodes"][0]["properties"]["entity_type"] == "requirement"


def test_load_graph_networkx_caps_to_top_degree_nodes(tmp_path) -> None:
    import networkx as nx

    workspace_dir = tmp_path / "demo"
    workspace_dir.mkdir()
    graph = nx.Graph()
    graph.add_node("hub", entity_id="HUB")
    for index in range(4):
        node = f"leaf-{index}"
        graph.add_node(node, entity_id=node)
        graph.add_edge("hub", node, keywords="RELATED_TO")
    nx.write_graphml(graph, workspace_dir / "graph_chunk_entity_relation.graphml")

    payload = load_graph_networkx("demo", 2, None, working_dir=tmp_path)

    node_ids = {node["id"] for node in payload["nodes"]}
    assert payload["total_nodes"] == 5
    assert payload["returned_nodes"] == 2
    assert payload["is_truncated"] is True
    assert "hub" in node_ids


def test_graph_route_uses_networkx_loader_for_missing_graph(tmp_path) -> None:
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
        "backend": "networkx",
        "workspace": "empty",
        "nodes": [],
        "edges": [],
        "total_nodes": 0,
        "returned_nodes": 0,
        "returned_edges": 0,
        "is_truncated": False,
    }
