import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.workspace_routes import (
    discover_workspaces,
    register_workspace_ui_routes,
    safe_count_json_keys,
    set_env_var,
)


def _client(
    tmp_path: Path,
    *,
    active: str = "active",
    set_calls: list[tuple[str, str]] | None = None,
    restart_calls: list[float] | None = None,
    inventory_func=None,
    delete_workspace_func=None,
    ensure_active_workspace=None,
) -> TestClient:
    app = FastAPI()
    register_workspace_ui_routes(
        app,
        workspace_name=lambda: active,
        working_dir=lambda: tmp_path,
        graph_storage=lambda: "NetworkXStorage",
        set_env_var_func=lambda key, value: set_calls.append((key, value)) if set_calls is not None else None,
        schedule_restart=lambda delay: restart_calls.append(delay) if restart_calls is not None else None,
        **({"inventory_func": inventory_func} if inventory_func else {}),
        **({"delete_workspace_func": delete_workspace_func} if delete_workspace_func else {}),
        **({"ensure_active_workspace": ensure_active_workspace} if ensure_active_workspace else {}),
    )
    return TestClient(app)


def test_safe_count_json_keys_handles_lightrag_shapes(tmp_path) -> None:
    kv_path = tmp_path / "kv.json"
    vdb_path = tmp_path / "vdb.json"
    list_path = tmp_path / "list.json"
    kv_path.write_text(json.dumps({"a": {}, "b": {}}), encoding="utf-8")
    vdb_path.write_text(json.dumps({"embedding_dim": 3, "data": [{}, {}, {}]}), encoding="utf-8")
    list_path.write_text(json.dumps([1, 2, 3, 4]), encoding="utf-8")

    assert safe_count_json_keys(kv_path) == 2
    assert safe_count_json_keys(vdb_path) == 3
    assert safe_count_json_keys(list_path) == 4
    assert safe_count_json_keys(tmp_path / "missing.json") == 0


def test_discover_workspaces_reports_data_and_skips_private_dirs(tmp_path) -> None:
    alpha = tmp_path / "alpha"
    alpha.mkdir()
    (alpha / "kv_store_doc_status.json").write_text(json.dumps({"doc": {}}), encoding="utf-8")
    (alpha / "vdb_entities.json").write_text(json.dumps({"data": [{}, {}]}), encoding="utf-8")
    chats = alpha / "chats"
    chats.mkdir()
    (chats / "one.json").write_text("{}", encoding="utf-8")
    (tmp_path / "_platform").mkdir()

    assert discover_workspaces(tmp_path) == [
        {
            "name": "alpha",
            "has_data": True,
            "documents": 1,
            "entities": 2,
            "chats": 1,
        }
    ]


def test_workspace_list_and_switch_routes_use_injected_callbacks(tmp_path) -> None:
    (tmp_path / "existing").mkdir()
    set_calls: list[tuple[str, str]] = []
    restart_calls: list[float] = []
    client = _client(tmp_path, set_calls=set_calls, restart_calls=restart_calls)

    list_response = client.get("/api/ui/workspaces")
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["active"] == "active"
    assert [item["name"] for item in list_response.json()["workspaces"]] == ["existing"]

    switch_response = client.post(
        "/api/ui/workspaces/switch",
        json={"name": "new_ws", "create": True},
    )
    assert switch_response.status_code == 200, switch_response.text
    assert switch_response.json()["status"] == "restarting"
    assert (tmp_path / "new_ws").is_dir()
    assert set_calls == [("WORKSPACE", "new_ws")]
    assert restart_calls == [0.75]


def test_workspace_switch_rejects_invalid_or_missing_workspace(tmp_path) -> None:
    client = _client(tmp_path)

    invalid = client.post("/api/ui/workspaces/switch", json={"name": "../bad"})
    missing = client.post("/api/ui/workspaces/switch", json={"name": "missing"})

    assert invalid.status_code == 400
    assert missing.status_code == 404


def test_inventory_delete_wipe_and_restart_routes_are_injected(tmp_path) -> None:
    restart_calls: list[float] = []
    delete_calls: list[tuple[str, dict[str, Any], str]] = []
    ensured: list[str] = []

    def inventory_func(*, active_workspace: str, graph_storage: str) -> dict[str, Any]:
        return {
            "active": active_workspace,
            "rag_storage_root": "rag_storage",
            "inputs_root": "inputs",
            "neo4j_available": "neo4j" in graph_storage.lower(),
            "workspaces": [
                {"name": "old", "is_active": False},
                {"name": active_workspace, "is_active": True},
            ],
        }

    def delete_workspace_func(name: str, scope, *, graph_storage: str) -> dict[str, Any]:
        delete_calls.append((name, scope.model_dump(), graph_storage))
        return {"workspace": name, "deleted": {"rag_storage": scope.rag_storage}}

    client = _client(
        tmp_path,
        restart_calls=restart_calls,
        inventory_func=inventory_func,
        delete_workspace_func=delete_workspace_func,
        ensure_active_workspace=lambda name: ensured.append(name),
    )

    inventory = client.get("/api/ui/workspaces/inventory")
    assert inventory.status_code == 200, inventory.text
    assert [row["name"] for row in inventory.json()["workspaces"]] == ["old", "active"]

    active_delete = client.post(
        "/api/ui/workspaces/active/delete",
        json={"rag_storage": True},
    )
    assert active_delete.status_code == 409

    delete = client.post(
        "/api/ui/workspaces/old/delete",
        json={"rag_storage": True},
    )
    assert delete.status_code == 200, delete.text
    assert delete.json() == {"workspace": "old", "deleted": {"rag_storage": True}}

    wipe = client.post(
        "/api/ui/workspaces/wipe-all",
        json={"rag_storage": True, "confirm": "DELETE ALL"},
    )
    assert wipe.status_code == 200, wipe.text
    assert wipe.json()["restarting"] is True
    assert restart_calls == [0.75]
    assert ensured == ["active"]
    assert [call[0] for call in delete_calls] == ["old", "old", "active"]

    restart = client.post("/api/ui/restart")
    assert restart.status_code == 200, restart.text
    assert restart.json()["status"] == "restarting"
    assert restart_calls == [0.75, 0.75]


def test_set_env_var_updates_env_file_and_process_env(tmp_path, monkeypatch) -> None:
    import src.server.workspace_routes as workspace_routes

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(workspace_routes, "reset_settings", lambda: None)
    (tmp_path / ".env").write_text("KEEP=1\nWORKSPACE=old\n# WORKSPACE=comment\n", encoding="utf-8")

    set_env_var("WORKSPACE", "new")

    assert (tmp_path / ".env").read_text(encoding="utf-8") == "KEEP=1\nWORKSPACE=new\n# WORKSPACE=comment\n"
    assert workspace_routes.os.environ["WORKSPACE"] == "new"
