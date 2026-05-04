from src.inference.neo4j_query_support import (
    run_count_query,
    run_mapped_query,
    run_projected_query,
)


class _Result:
    def __init__(self, records):
        self._records = list(records)

    def __iter__(self):
        return iter(self._records)

    def single(self):
        return self._records[0] if self._records else None


class _Session:
    def __init__(self, result):
        self._result = result
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self.calls.append((query, params))
        return self._result


class _Driver:
    def __init__(self, session):
        self._session = session
        self.database_calls = []

    def session(self, *, database):
        self.database_calls.append(database)
        return self._session


def test_run_mapped_query_maps_each_record() -> None:
    session = _Session(_Result([{"value": 1}, {"value": 2}]))
    driver = _Driver(session)

    result = run_mapped_query(
        driver,
        "neo4j",
        "RETURN 1",
        lambda record: record["value"] * 10,
        limit=2,
    )

    assert result == [10, 20]
    assert driver.database_calls == ["neo4j"]
    assert session.calls == [("RETURN 1", {"limit": 2})]


def test_run_projected_query_projects_full_result() -> None:
    session = _Session(_Result([{"value": "a"}, {"value": "b"}]))
    driver = _Driver(session)

    result = run_projected_query(
        driver,
        "neo4j",
        "RETURN x",
        lambda rows: [record["value"] for record in rows],
    )

    assert result == ["a", "b"]


def test_run_count_query_reads_single_count_record() -> None:
    session = _Session(_Result([{"created_count": 7}]))
    driver = _Driver(session)

    result = run_count_query(
        driver,
        "neo4j",
        "RETURN count(*) as created_count",
        lambda record, key: int(record[key]),
        "created_count",
        batch=3,
    )

    assert result == 7
    assert session.calls == [(
        "RETURN count(*) as created_count",
        {"batch": 3},
    )]