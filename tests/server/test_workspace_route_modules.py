"""Contract tests: workspace feature routes live in dedicated modules (#189)."""

from __future__ import annotations


def test_graph_routes_module_exports_register() -> None:
    from src.server.graph_routes import json_safe, register_graph_routes

    assert callable(register_graph_routes)
    assert json_safe({"x": 1}) == {"x": 1}


def test_entity_chunk_routes_module_exports_register() -> None:
    from src.server.entity_chunk_routes import load_entity_chunks, register_entity_chunk_routes

    assert callable(register_entity_chunk_routes)
    assert callable(load_entity_chunks)


def test_intelligence_routes_module_exports_register() -> None:
    from src.server.intelligence_routes import compute_intel, register_intelligence_routes

    assert callable(register_intelligence_routes)
    assert callable(compute_intel)


def test_workspace_ui_routes_module_exports_register() -> None:
    from src.server.workspace_ui_routes import register_workspace_ui_routes

    assert callable(register_workspace_ui_routes)


def test_workspace_maintenance_module_exports_deep_store() -> None:
    from src.server.workspace_maintenance import WorkspaceMaintenance, safe_count_json_keys

    assert WorkspaceMaintenance is not None
    assert safe_count_json_keys(__import__("pathlib").Path("missing.json")) == 0