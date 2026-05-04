from src.inference import neo4j_mutations as mutations_module
from src.inference.neo4j_mutations import (
    create_entities,
    create_relationships,
    retype_relationships,
)


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

    monkeypatch.setattr(
        mutations_module,
        "log_rejected_relationships",
        lambda relationships, rejected_relationships, *, logger: rejected_calls.append(
            (relationships, rejected_relationships)
        ),
    )

    count = create_relationships(
        driver,
        "neo4j",
        "workspace",
        [
            {"source_id": "a", "target_id": "b", "relationship_type": "GUIDES", "reasoning": "good"},
            {"source_id": "a", "target_id": "c", "relationship_type": "", "reasoning": "bad"},
        ],
        logger=_Logger(),
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

    count = retype_relationships(
        driver,
        "neo4j",
        "workspace",
        [
            {"source_id": "a", "target_id": "b", "old_type": "RELATED_TO", "new_type": "GUIDES"},
            {"source_id": "c", "target_id": "d", "old_type": "RELATED_TO", "new_type": "SATISFIED_BY"},
            {"source_id": "e", "target_id": "f", "old_type": "RELATED_TO", "new_type": "SATISFIED_BY"},
        ],
        logger=_Logger(),
    )

    assert count == 3
    assert len(session.calls) == 2
    assert {call[1]["new_type"] for call in session.calls} == {"GUIDES", "SATISFIED_BY"}


def test_create_entities_rejects_missing_names_before_write(monkeypatch) -> None:
    rejected_entities = []
    session = _Session([_Result([{"created_count": 1}])])
    driver = _Driver(session)

    monkeypatch.setattr(
        mutations_module,
        "log_rejected_entities",
        lambda entities, *, logger: rejected_entities.append(entities),
    )

    count = create_entities(
        driver,
        "neo4j",
        "workspace",
        [
            {"entity_name": "REQ-1", "entity_type": "requirement"},
            {"entity_name": "", "entity_type": "requirement"},
        ],
        logger=_Logger(),
    )

    assert count == 1
    assert session.calls[0][1]["entities"] == [
        {"entity_name": "REQ-1", "entity_type": "requirement"}
    ]
    assert rejected_entities == [[{"entity_name": "", "entity_type": "requirement"}]]
