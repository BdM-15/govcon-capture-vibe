"""Tests for the neo4j_entity_label_patch monkey-patch module."""

from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.neo4j_entity_label_patch import (
    _sanitize_label,
    install_neo4j_entity_label_patch,
    _patched_upsert_node,
    _patched_upsert_nodes_batch,
)


# ---------------------------------------------------------------------------
# _sanitize_label
# ---------------------------------------------------------------------------


class TestSanitizeLabel:
    def test_clean_label_unchanged(self) -> None:
        assert _sanitize_label("requirement") == "requirement"

    def test_backticks_stripped(self) -> None:
        assert _sanitize_label("`requirement`") == "requirement"

    def test_comma_separated_takes_first(self) -> None:
        assert _sanitize_label("requirement, deliverable") == "requirement"

    def test_empty_becomes_unknown(self) -> None:
        assert _sanitize_label("") == "UNKNOWN"

    def test_whitespace_only_becomes_unknown(self) -> None:
        assert _sanitize_label("   ") == "UNKNOWN"

    def test_backtick_and_comma_sanitized(self) -> None:
        assert _sanitize_label("`req`, `del`") == "req"

    def test_numeric_string_passthrough(self) -> None:
        # Entity types are strings; numeric values shouldn't crash
        assert _sanitize_label("42") == "42"


# ---------------------------------------------------------------------------
# _patched_upsert_node — verifies SET n:`{entity_type}` is in the query
# ---------------------------------------------------------------------------


def _make_fake_storage(workspace: str = "test_ws") -> Any:
    """Build a minimal fake Neo4JStorage-like object for testing."""
    storage = MagicMock()
    storage.workspace = workspace
    storage._DATABASE = "neo4j"
    storage._get_workspace_label.return_value = workspace

    # Capture the Cypher query that gets executed
    storage._last_query: str = ""
    storage._last_params: dict = {}

    async def fake_run(query, **kwargs):
        storage._last_query = query
        storage._last_params = kwargs
        result = AsyncMock()
        result.consume = AsyncMock()
        return result

    tx = AsyncMock()
    tx.run = AsyncMock(side_effect=fake_run)

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session_cm)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    async def fake_execute_write(fn, *args, **kwargs):
        await fn(tx, *args, **kwargs)

    session_cm.execute_write = AsyncMock(side_effect=fake_execute_write)

    storage._driver = MagicMock()
    storage._driver.session.return_value = session_cm

    return storage


class TestPatchedUpsertNode:
    def test_query_contains_entity_type_label(self) -> None:
        storage = _make_fake_storage("ws1")
        node_data = {"entity_id": "req-1", "entity_type": "requirement", "name": "FR-1"}

        asyncio.run(_patched_upsert_node(storage, "req-1", node_data))

        assert "SET n:`requirement`" in storage._last_query

    def test_query_contains_workspace_label(self) -> None:
        storage = _make_fake_storage("ws1")
        node_data = {"entity_id": "req-1", "entity_type": "requirement"}

        asyncio.run(_patched_upsert_node(storage, "req-1", node_data))

        assert "MERGE (n:`ws1`" in storage._last_query

    def test_missing_entity_id_raises(self) -> None:
        storage = _make_fake_storage()
        with pytest.raises(ValueError, match="entity_id"):
            asyncio.run(_patched_upsert_node(storage, "x", {"entity_type": "requirement"}))

    def test_entity_type_sanitized_before_label(self) -> None:
        storage = _make_fake_storage("ws1")
        node_data = {"entity_id": "n1", "entity_type": "`bad, type`"}

        asyncio.run(_patched_upsert_node(storage, "n1", node_data))

        assert "SET n:`bad`" in storage._last_query

    def test_null_entity_type_uses_unknown(self) -> None:
        storage = _make_fake_storage("ws1")
        node_data = {"entity_id": "n1", "entity_type": None}

        asyncio.run(_patched_upsert_node(storage, "n1", node_data))

        assert "SET n:`UNKNOWN`" in storage._last_query


# ---------------------------------------------------------------------------
# _patched_upsert_nodes_batch — verifies labels appear in per-type queries
# ---------------------------------------------------------------------------


class TestPatchedUpsertNodesBatch:
    def _collect_queries(self, nodes: list[tuple[str, dict]]) -> list[str]:
        storage = _make_fake_storage("ws_batch")
        queries: list[str] = []

        async def recording_execute_write(fn, *args, **kwargs):
            tx = AsyncMock()
            captured: list[str] = []

            async def fake_run(q, **kw):
                captured.append(q)
                r = AsyncMock()
                r.consume = AsyncMock()
                return r

            tx.run = AsyncMock(side_effect=fake_run)
            await fn(tx, *args, **kwargs)
            queries.extend(captured)

        session_cm = AsyncMock()
        session_cm.__aenter__ = AsyncMock(return_value=session_cm)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        session_cm.execute_write = AsyncMock(side_effect=recording_execute_write)
        storage._driver.session.return_value = session_cm

        asyncio.run(_patched_upsert_nodes_batch(storage, nodes))
        return queries

    def test_each_type_gets_its_label(self) -> None:
        nodes = [
            ("r1", {"entity_id": "r1", "entity_type": "requirement"}),
            ("d1", {"entity_id": "d1", "entity_type": "deliverable"}),
            ("r2", {"entity_id": "r2", "entity_type": "requirement"}),
        ]
        queries = self._collect_queries(nodes)

        # Two distinct types → two queries
        assert len(queries) == 2
        labels_in_queries = {q.split("SET n:`")[1].split("`")[0] for q in queries}
        assert labels_in_queries == {"requirement", "deliverable"}

    def test_empty_list_is_noop(self) -> None:
        storage = _make_fake_storage()
        asyncio.run(_patched_upsert_nodes_batch(storage, []))
        storage._driver.session.assert_not_called()

    def test_missing_entity_id_raises(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            asyncio.run(
                _patched_upsert_nodes_batch(
                    _make_fake_storage(), [("x", {"entity_type": "requirement"})]
                )
            )

    def test_workspace_label_in_merge(self) -> None:
        nodes = [("n1", {"entity_id": "n1", "entity_type": "clause"})]
        queries = self._collect_queries(nodes)
        assert "MERGE (n:`ws_batch`" in queries[0]


# ---------------------------------------------------------------------------
# install_neo4j_entity_label_patch
# ---------------------------------------------------------------------------


class TestInstallPatch:
    def setup_method(self) -> None:
        # Reset the guard so the patch can be applied fresh in each test.
        import src.server.neo4j_entity_label_patch as mod

        mod._PATCH_APPLIED = False

    def teardown_method(self) -> None:
        # Restore originals so other tests aren't affected.
        import src.server.neo4j_entity_label_patch as mod

        mod._PATCH_APPLIED = False
        try:
            from lightrag.kg.neo4j_impl import Neo4JStorage

            Neo4JStorage.upsert_node = _orig_upsert_node
            Neo4JStorage.upsert_nodes_batch = _orig_upsert_nodes_batch
        except ImportError:
            pass

    def test_patch_replaces_upsert_node(self) -> None:
        try:
            from lightrag.kg.neo4j_impl import Neo4JStorage
        except ImportError:
            pytest.skip("lightrag neo4j_impl not available in this environment")

        install_neo4j_entity_label_patch()

        assert Neo4JStorage.upsert_node is _patched_upsert_node

    def test_patch_replaces_upsert_nodes_batch(self) -> None:
        try:
            from lightrag.kg.neo4j_impl import Neo4JStorage
        except ImportError:
            pytest.skip("lightrag neo4j_impl not available in this environment")

        install_neo4j_entity_label_patch()

        assert Neo4JStorage.upsert_nodes_batch is _patched_upsert_nodes_batch

    def test_install_is_idempotent(self) -> None:
        try:
            from lightrag.kg.neo4j_impl import Neo4JStorage
        except ImportError:
            pytest.skip("lightrag neo4j_impl not available in this environment")

        install_neo4j_entity_label_patch()
        first = Neo4JStorage.upsert_node

        install_neo4j_entity_label_patch()
        assert Neo4JStorage.upsert_node is first


# Capture originals so teardown can restore them.
try:
    from lightrag.kg.neo4j_impl import Neo4JStorage as _Neo4JStorage

    _orig_upsert_node = _Neo4JStorage.upsert_node
    _orig_upsert_nodes_batch = getattr(_Neo4JStorage, "upsert_nodes_batch", None)
except ImportError:
    _orig_upsert_node = None
    _orig_upsert_nodes_batch = None
