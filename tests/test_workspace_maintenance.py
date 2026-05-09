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
            "pursuit": None,
        }
    ]
    assert closed == ["closed"]


def test_workspace_maintenance_ensure_active_storage_workspace_scaffolds_pursuit_template(monkeypatch, tmp_path) -> None:
    rag_root = tmp_path / "rag_storage"
    monkeypatch.setattr(maintenance_module, "_rag_storage_root", lambda: rag_root)

    maintenance = WorkspaceMaintenance()
    maintenance.ensure_active_storage_workspace("demo")

    pursuit_root = rag_root / "demo" / "pursuits" / "demo"
    pursuit_file = pursuit_root / "00_pursuit.yaml"
    assert pursuit_file.is_file()
    for folder in (
        "01-identify",
        "02-qualify",
        "03-capture",
        "04-proposal",
        "05-submitted",
        "06-award",
    ):
        assert (pursuit_root / folder).is_dir()
    content = pursuit_file.read_text(encoding="utf-8")
    assert "pwin_drivers:" in content
    assert "shipley_folders:" in content


def test_workspace_maintenance_inventory_reads_pursuit_metadata(monkeypatch, tmp_path) -> None:
    rag_root = tmp_path / "rag_storage"
    inputs_root = tmp_path / "inputs"
    workspace_root = rag_root / "old"
    pursuit_root = workspace_root / "pursuits" / "old"
    pursuit_root.mkdir(parents=True)
    (pursuit_root / "00_pursuit.yaml").write_text(
        "\n".join(
            [
                "workspace: old",
                "slug: old",
                "title: Old Pursuit",
                "agency: Air Force",
                "stage: capture",
                "gate:",
                "  name: pursuit",
                "  due: 2026-05-31",
                "proposal_due: 2026-06-15",
                "pwin:",
                "  confidence: high",
                "  trend: up",
                "pwin_drivers:",
                "  - key: customer",
                "    label: Customer relationship",
                "    weight: 30",
                "    score: 5",
                "    rationale: Customer is already opening doors.",
                "    next_action: Keep weekly touchpoints.",
                "  - key: solution",
                "    label: Solution fit",
                "    weight: 30",
                "    score: 4",
                "  - key: competition",
                "    label: Competitive position",
                "    weight: 25",
                "    score: 3",
                "  - key: price",
                "    label: Price realism",
                "    weight: 15",
                "    score: 2",
                "readiness:",
                "  customer: 5",
                "  compete: 4",
                "  solution: 4",
                "  team: 3",
                "  price: 2",
                "  compliance: 3",
                "  proposal: 2",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(maintenance_module, "_rag_storage_root", lambda: rag_root)
    monkeypatch.setattr(maintenance_module, "_inputs_root", lambda: inputs_root)
    monkeypatch.setattr(maintenance_module, "_storage_workspaces", lambda root: {"old": 12.5})
    monkeypatch.setattr(maintenance_module, "_inputs_workspaces", lambda root: {"old": (0, 0.0)})

    maintenance = WorkspaceMaintenance()
    result = maintenance.workspace_inventory(
        active_workspace="old",
        graph_storage="NetworkXStorage",
    )

    row = result["workspaces"][0]
    assert row["pursuit"] == {
        "workspace": "old",
        "slug": "old",
        "title": "Old Pursuit",
        "agency": "Air Force",
        "stage": "capture",
        "source_path": "pursuits/old/00_pursuit.yaml",
        "gate": {"name": "pursuit", "due": "2026-05-31"},
        "proposal_due": "2026-06-15",
        "pwin": {"value": 75, "confidence": "high", "trend": "up"},
        "pwin_drivers": [
            {
                "key": "customer",
                "label": "Customer relationship",
                "weight": 30,
                "score": 5,
                "rationale": "Customer is already opening doors.",
                "next_action": "Keep weekly touchpoints.",
            },
            {
                "key": "solution",
                "label": "Solution fit",
                "weight": 30,
                "score": 4,
                "rationale": None,
                "next_action": None,
            },
            {
                "key": "competition",
                "label": "Competitive position",
                "weight": 25,
                "score": 3,
                "rationale": None,
                "next_action": None,
            },
            {
                "key": "price",
                "label": "Price realism",
                "weight": 15,
                "score": 2,
                "rationale": None,
                "next_action": None,
            },
        ],
        "readiness": {
            "customer": 5,
            "compete": 4,
            "solution": 4,
            "team": 3,
            "price": 2,
            "compliance": 3,
            "proposal": 2,
        },
        "shipley_folders": [
            "01-identify",
            "02-qualify",
            "03-capture",
            "04-proposal",
            "05-submitted",
            "06-award",
        ],
    }


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