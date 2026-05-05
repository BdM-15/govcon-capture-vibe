from types import SimpleNamespace

from src.server import workspace_routes as maintenance_module
from src.server.workspace_routes import WorkspaceMaintenance


def test_workspace_maintenance_inventory_aggregates_sources(monkeypatch) -> None:
    closed: list[str] = []

    class FakeGraphIO:
        database = "neo4j"

        def close(self) -> None:
            closed.append("closed")

    monkeypatch.setattr(maintenance_module, "_rag_storage_root", lambda: maintenance_module.Path("rag_storage"))
    monkeypatch.setattr(maintenance_module, "_inputs_root", lambda: maintenance_module.Path("inputs"))
    monkeypatch.setattr(maintenance_module, "_storage_workspaces", lambda root: {"old": 12.5})
    monkeypatch.setattr(maintenance_module, "_inputs_workspaces", lambda root: {"old": (3, 1.2)})
    monkeypatch.setattr(maintenance_module, "_neo4j_workspaces", lambda io: {"old": 7})

    maintenance = WorkspaceMaintenance(graph_io_factory=FakeGraphIO)
    result = maintenance.workspace_inventory(
        active_workspace="active",
        graph_storage="Neo4JStorage",
    )

    assert result["neo4j_available"] is True
    assert result["workspaces"] == [
        {
            "name": "old",
            "is_active": False,
            "neo4j_nodes": 7,
            "storage_mb": 12.5,
            "inputs_files": 3,
            "inputs_mb": 1.2,
        }
    ]
    assert closed == ["closed"]


def test_workspace_maintenance_delete_workspace_collects_bucket_results(monkeypatch) -> None:
    closed: list[str] = []

    class FakeGraphIO:
        def close(self) -> None:
            closed.append("closed")

    monkeypatch.setattr(maintenance_module, "_rag_storage_root", lambda: maintenance_module.Path("rag_storage"))
    monkeypatch.setattr(maintenance_module, "_inputs_root", lambda: maintenance_module.Path("inputs"))
    monkeypatch.setattr(maintenance_module, "_delete_neo4j_workspace", lambda io, name: 9)
    monkeypatch.setattr(maintenance_module, "_delete_storage_workspace", lambda name, root: True)
    monkeypatch.setattr(maintenance_module, "_delete_inputs_workspace", lambda name, root: (4, 2.5))
    monkeypatch.setattr(
        maintenance_module.Path,
        "iterdir",
        lambda self: iter(()),
    )

    maintenance = WorkspaceMaintenance(graph_io_factory=FakeGraphIO)
    scope = SimpleNamespace(neo4j=True, rag_storage=True, inputs=True)
    result = maintenance.delete_workspace("old", scope, graph_storage="Neo4JStorage")

    assert result == {
        "workspace": "old",
        "deleted": {
            "neo4j_nodes": 9,
            "rag_storage": True,
            "inputs_files": 4,
            "inputs_mb": 2.5,
        },
    }
    assert closed == ["closed"]