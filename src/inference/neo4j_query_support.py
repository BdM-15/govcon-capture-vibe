"""Shared Neo4j query runners used by graph I/O methods."""

from __future__ import annotations

from typing import Any, Callable


def run_mapped_query(
    driver,
    database: str,
    query: str,
    row_mapper: Callable[[Any], Any],
    **params,
) -> list[Any]:
    """Run query and map each row through ``row_mapper``."""
    with driver.session(database=database) as session:
        result = session.run(query, **params)
        return [row_mapper(record) for record in result]


def run_projected_query(
    driver,
    database: str,
    query: str,
    projector: Callable[[Any], Any],
    **params,
) -> Any:
    """Run query and project full result through ``projector``."""
    with driver.session(database=database) as session:
        result = session.run(query, **params)
        return projector(result)


def run_count_query(
    driver,
    database: str,
    query: str,
    count_reader: Callable[[Any | None, str], int],
    result_key: str,
    **params,
) -> int:
    """Run query returning one count row and read it with ``count_reader``."""
    with driver.session(database=database) as session:
        result = session.run(query, **params)
        return count_reader(result.single(), result_key)