from src.inference import neo4j_graph_io as graph_io_module
from src.inference.neo4j_graph_io import Neo4jGraphIO


def test_neo4j_graph_io_delegates_mutations(monkeypatch) -> None:
    calls = []

    def _stub(name, result):
        def _inner(driver, database, workspace, payload, *, logger):
            calls.append((name, driver, database, workspace, payload, logger))
            return result

        return _inner

    monkeypatch.setattr(graph_io_module, "update_entity_types", _stub("update_entity_types", 1))
    monkeypatch.setattr(graph_io_module, "update_entity_properties", _stub("update_entity_properties", 2))
    monkeypatch.setattr(graph_io_module, "create_relationships", _stub("create_relationships", 3))
    monkeypatch.setattr(graph_io_module, "retype_relationships", _stub("retype_relationships", 4))
    monkeypatch.setattr(graph_io_module, "enrich_entity_metadata", _stub("enrich_entity_metadata", 5))
    monkeypatch.setattr(graph_io_module, "create_entities", _stub("create_entities", 6))
    monkeypatch.setattr(graph_io_module, "create_typed_relationships", _stub("create_typed_relationships", 7))

    graph_io = Neo4jGraphIO.__new__(Neo4jGraphIO)
    graph_io.driver = object()
    graph_io.database = "neo4j"
    graph_io.workspace = "workspace"

    assert graph_io.update_entity_types([{"id": "1"}]) == 1
    assert graph_io.update_entity_properties([{"id": "1"}]) == 2
    assert graph_io.create_relationships([{"source_id": "a", "target_id": "b"}]) == 3
    assert graph_io.retype_relationships([{"source_id": "a", "target_id": "b"}]) == 4
    assert graph_io.enrich_entity_metadata([{"id": "1"}]) == 5
    assert graph_io.create_entities([{"entity_name": "REQ-1"}]) == 6
    assert graph_io.create_typed_relationships([{"source_entity": "REQ-1"}]) == 7

    assert [call[0] for call in calls] == [
        "update_entity_types",
        "update_entity_properties",
        "create_relationships",
        "retype_relationships",
        "enrich_entity_metadata",
        "create_entities",
        "create_typed_relationships",
    ]
    assert all(call[2] == "neo4j" for call in calls)
    assert all(call[3] == "workspace" for call in calls)
