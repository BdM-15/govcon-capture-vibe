from src.inference import neo4j_graph_io as graph_io_module
from src.inference.neo4j_graph_io import Neo4jGraphIO


def test_neo4j_graph_io_write_methods_keep_workspace_context(monkeypatch) -> None:
    calls = []

    def fake_run_count_query(driver, database, query, mapper, key, **params):
        calls.append((database, query, params))
        return len(calls)

    monkeypatch.setattr(graph_io_module, "run_count_query", fake_run_count_query)

    graph_io = Neo4jGraphIO.__new__(Neo4jGraphIO)
    graph_io.driver = object()
    graph_io.database = "neo4j"
    graph_io.workspace = "workspace"

    assert graph_io.update_entity_types([{"id": "1"}]) == 1
    assert graph_io.update_entity_properties([{"id": "1"}]) == 2
    assert graph_io.update_entity_names([{"id": "1", "new_entity_name": "REQ-1"}]) == 3
    assert graph_io.create_entities([{"entity_name": "REQ-1", "entity_type": "requirement"}]) == 4
    assert graph_io.create_typed_relationships([{"source_entity": "REQ-1", "target_entity": "REQ-2", "relationship_type": "GUIDES"}]) == 5

    assert all(call[0] == "neo4j" for call in calls)
    assert all("workspace" in call[1] for call in calls)
    assert calls[0][2] == {"updates": [{"id": "1"}]}
    assert calls[1][2] == {"updates": [{"id": "1"}]}
    assert calls[2][2] == {"updates": [{"id": "1", "new_entity_name": "REQ-1"}]}
    assert calls[3][2] == {"entities": [{"entity_name": "REQ-1", "entity_type": "requirement"}]}
    assert calls[4][2] == {
        "relationships": [
            {"source_entity": "REQ-1", "target_entity": "REQ-2", "relationship_type": "GUIDES"}
        ]
    }


class _Result:
    def __init__(self, records):
        self._records = list(records)

    def single(self):
        return self._records[0] if self._records else None


class _Session:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self.calls.append((query, params))
        return self._results.pop(0)


class _Driver:
    def __init__(self, session):
        self._session = session
        self.database_calls = []

    def session(self, *, database):
        self.database_calls.append(database)
        return self._session


class _Logger:
    def __init__(self) -> None:
        self.info_messages: list[str] = []
        self.warning_messages: list[str] = []

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def warning(self, message: str) -> None:
        self.warning_messages.append(message)


def test_create_relationships_filters_invalid_types_before_write(monkeypatch) -> None:
    rejected_calls = []
    session = _Session([_Result([{"created_count": 1}])])
    driver = _Driver(session)
    graph_io = Neo4jGraphIO.__new__(Neo4jGraphIO)
    graph_io.driver = driver
    graph_io.database = "neo4j"
    graph_io.workspace = "workspace"

    monkeypatch.setattr(
        graph_io_module,
        "log_rejected_relationships",
        lambda relationships, rejected_relationships, *, logger: rejected_calls.append(
            (relationships, rejected_relationships)
        ),
    )

    count = graph_io.create_relationships(
        [
            {"source_id": "a", "target_id": "b", "relationship_type": "GUIDES", "reasoning": "good"},
            {"source_id": "a", "target_id": "c", "relationship_type": "", "reasoning": "bad"},
        ]
    )

    assert count == 1
    assert driver.database_calls == ["neo4j"]
    assert session.calls[0][1]["relationships"] == [
        {"source_id": "a", "target_id": "b", "relationship_type": "GUIDES", "reasoning": "good"}
    ]
    assert rejected_calls == [
        (
            [
                {"source_id": "a", "target_id": "b", "relationship_type": "GUIDES", "reasoning": "good"},
                {"source_id": "a", "target_id": "c", "relationship_type": "", "reasoning": "bad"},
            ],
            [{"source_id": "a", "target_id": "c", "relationship_type": "", "reasoning": "bad"}],
        )
    ]


def test_retype_relationships_batches_by_old_and_new_type() -> None:
    session = _Session([
        _Result([{"retyped_count": 1}]),
        _Result([{"retyped_count": 2}]),
    ])
    driver = _Driver(session)
    graph_io = Neo4jGraphIO.__new__(Neo4jGraphIO)
    graph_io.driver = driver
    graph_io.database = "neo4j"
    graph_io.workspace = "workspace"

    count = graph_io.retype_relationships(
        [
            {"source_id": "a", "target_id": "b", "old_type": "RELATED_TO", "new_type": "GUIDES"},
            {"source_id": "c", "target_id": "d", "old_type": "RELATED_TO", "new_type": "SATISFIED_BY"},
            {"source_id": "e", "target_id": "f", "old_type": "RELATED_TO", "new_type": "SATISFIED_BY"},
        ]
    )

    assert count == 3
    assert len(session.calls) == 2
    assert {call[1]["new_type"] for call in session.calls} == {"GUIDES", "SATISFIED_BY"}


def test_create_entities_rejects_missing_names_before_write(monkeypatch) -> None:
    rejected_entities = []
    graph_io = Neo4jGraphIO.__new__(Neo4jGraphIO)
    graph_io.driver = object()
    graph_io.database = "neo4j"
    graph_io.workspace = "workspace"

    monkeypatch.setattr(
        graph_io_module,
        "log_rejected_entities",
        lambda entities, *, logger: rejected_entities.append(entities),
    )
    monkeypatch.setattr(
        graph_io_module,
        "run_count_query",
        lambda driver, database, query, mapper, key, **params: len(params["entities"]),
    )

    count = graph_io.create_entities(
        [
            {"entity_name": "REQ-1", "entity_type": "requirement"},
            {"entity_name": "", "entity_type": "requirement"},
        ]
    )

    assert count == 1
    assert rejected_entities == [[{"entity_name": "", "entity_type": "requirement"}]]
