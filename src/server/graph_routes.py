"""Knowledge graph snapshot routes for Capture Workbench."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from src.core.neo4j_config import get_neo4j_connection_config
from src.server.workspace_maintenance import SYSTEM_LABELS

logger = logging.getLogger(__name__)

GRAPH_HARD_CAP = 5000
GRAPH_DEFAULT = 2000


def json_safe(value: Any) -> Any:
    """Coerce neo4j/numpy/datetime values into JSON-serializable scalars."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    for attr in ("isoformat", "iso_format", "to_native"):
        if hasattr(value, attr):
            try:
                coerced = getattr(value, attr)()
                if isinstance(coerced, datetime):
                    return coerced.isoformat()
                return json_safe(coerced)
            except Exception:  # noqa: BLE001
                pass
    try:
        return str(value)
    except Exception:  # noqa: BLE001
        return None


async def load_graph_neo4j(
    workspace: str,
    max_nodes: int,
    entity_type: str | None,
) -> dict[str, Any]:
    """Pull Cytoscape-friendly subgraph from Neo4j, top-degree nodes first."""
    from neo4j import AsyncGraphDatabase

    config = get_neo4j_connection_config()
    label = workspace

    type_filter = ""
    params: dict[str, Any] = {"max_nodes": int(max_nodes)}
    if entity_type:
        type_filter = "WHERE toLower(n.entity_type) = toLower($etype)"
        params["etype"] = entity_type

    nodes_query = f"""
        MATCH (n:`{label}`)
        {type_filter}
        WITH n, COUNT {{ (n)--() }} AS degree
        ORDER BY degree DESC
        LIMIT $max_nodes
        RETURN elementId(n) AS nid, n AS node, degree
    """
    total_query = f"MATCH (n:`{label}`) {type_filter} RETURN count(n) AS total"
    edges_query = f"""
        MATCH (a:`{label}`)-[r]->(b:`{label}`)
        WHERE elementId(a) IN $ids AND elementId(b) IN $ids
        RETURN elementId(r) AS rid, elementId(a) AS src, elementId(b) AS tgt,
               type(r) AS rtype, properties(r) AS props
    """

    driver = AsyncGraphDatabase.driver(config.uri, auth=config.auth)
    try:
        async with driver.session(database=config.database, default_access_mode="READ") as session:
            total_res = await session.run(
                total_query,
                **({"etype": entity_type} if entity_type else {}),
            )
            total = (await total_res.single())["total"]
            await total_res.consume()

            nodes_res = await session.run(nodes_query, **params)
            nodes_payload: list[dict[str, Any]] = []
            ids: list[str] = []
            async for record in nodes_res:
                node_id = record["nid"]
                props = json_safe(dict(record["node"]))
                ids.append(node_id)
                nodes_payload.append(
                    {
                        "id": str(node_id),
                        "labels": [str(props.get("entity_id", node_id))],
                        "properties": {
                            **props,
                            "_degree": int(record["degree"] or 0),
                        },
                    }
                )
            await nodes_res.consume()

            edges_payload: list[dict[str, Any]] = []
            if ids:
                edges_res = await session.run(edges_query, ids=ids)
                async for record in edges_res:
                    edges_payload.append(
                        {
                            "id": str(record["rid"]),
                            "source": str(record["src"]),
                            "target": str(record["tgt"]),
                            "type": record["rtype"],
                            "properties": json_safe(dict(record["props"] or {})),
                        }
                    )
                await edges_res.consume()
    finally:
        await driver.close()

    return {
        "backend": "neo4j",
        "workspace": workspace,
        "nodes": nodes_payload,
        "edges": edges_payload,
        "total_nodes": int(total),
        "returned_nodes": len(nodes_payload),
        "returned_edges": len(edges_payload),
        "is_truncated": int(total) > len(nodes_payload),
    }


def empty_graph_snapshot(workspace: str, *, backend: str) -> dict[str, Any]:
    """Return an empty Cytoscape payload when Neo4j is not the active graph backend."""
    return {
        "backend": backend,
        "workspace": workspace,
        "nodes": [],
        "edges": [],
        "total_nodes": 0,
        "returned_nodes": 0,
        "returned_edges": 0,
        "is_truncated": False,
    }


_GRASS_PATH = Path(__file__).parent.parent / "ui" / "static" / "neo4j-style.grass"
_WORKSPACE_LABEL_RULE = (
    "node.{label} {{\n"
    "  color: #1E293B;\n"
    "  border-color: #0F172A;\n"
    "  text-color-internal: #64748B;\n"
    "  font-size: 8px;\n"
    "  diameter: 38px;\n"
    "  caption: \"{{entity_id}}\";\n"
    "}}\n"
)


async def _get_all_workspace_labels() -> list[str]:
    """Return all Neo4j labels that are not govcon entity types or system labels."""
    from src.ontology.schema import VALID_ENTITY_TYPES  # noqa: PLC0415

    entity_set = {e.lower() for e in VALID_ENTITY_TYPES} | SYSTEM_LABELS
    try:
        cfg = get_neo4j_connection_config()
        from neo4j import AsyncGraphDatabase  # noqa: PLC0415

        driver = AsyncGraphDatabase.driver(cfg.uri, auth=cfg.auth)
        try:
            async with driver.session(database=cfg.database) as session:
                result = await session.run("CALL db.labels() YIELD label RETURN label")
                rows = await result.data()
                return [r["label"] for r in rows if r["label"].lower() not in entity_set]
        finally:
            await driver.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch workspace labels for GraSS: %s", exc)
        return []


def register_graph_routes(
    app: FastAPI,
    *,
    workspace_name: Callable[[], str],
    graph_storage: Callable[[], str],
    working_dir: Callable[[], Path],
) -> None:
    """Register graph snapshot route for Theseus UI."""

    @app.get("/api/ui/neo4j-style.grass", tags=["theseus-ui"])
    async def neo4j_grass() -> "PlainTextResponse":
        """Serve GraSS with workspace labels prepended before entity-type rules.

        Neo4j Browser auto-generates a color rule for any label NOT in the
        loaded GraSS and appends it at the end — overriding entity-type rules
        (last-wins CSS cascade).  By fetching all current workspace labels from
        the DB and prepending a dark-navy rule for each, we prevent that
        auto-generation and let entity-type styles (listed later in the file) win.

        Usage in Neo4j Browser:
          :style reset
          :style http://localhost:9621/api/ui/neo4j-style.grass
        """
        from fastapi.responses import PlainTextResponse  # noqa: PLC0415

        static_grass = _GRASS_PATH.read_text(encoding="utf-8")
        workspace_labels = await _get_all_workspace_labels()

        if workspace_labels:
            ws_block = "/* ── Auto-prepended workspace labels (prevents Browser auto-generation) ── */\n\n"
            for lbl in sorted(workspace_labels):
                ws_block += _WORKSPACE_LABEL_RULE.format(label=lbl)
                ws_block += "\n"
            # Insert after the default node/relationship block and before the first entity-type group
            marker = "/* ── Workspace label"
            if marker in static_grass:
                # Replace the hand-edited workspace label section with the dynamic block
                start = static_grass.index(marker)
                # Find the next entity-type group comment
                next_group = static_grass.index("/* ──", start + len(marker))
                static_grass = static_grass[:start] + ws_block + static_grass[next_group:]
            else:
                # Prepend before the first entity-type rule
                static_grass = ws_block + static_grass

        return PlainTextResponse(static_grass, media_type="text/plain")

    @app.get("/api/ui/graph", tags=["theseus-ui"])
    async def ui_graph(
        max_nodes: int = GRAPH_DEFAULT,
        entity_type: str | None = None,
    ) -> JSONResponse:
        """Return Cytoscape-friendly subgraph for active workspace."""
        try:
            cap = max(1, min(int(max_nodes), GRAPH_HARD_CAP))
        except (TypeError, ValueError):
            cap = GRAPH_DEFAULT

        workspace = workspace_name()
        backend = (graph_storage() or "").lower()
        try:
            if "neo4j" in backend:
                payload = await load_graph_neo4j(workspace, cap, entity_type)
            else:
                payload = empty_graph_snapshot(
                    workspace,
                    backend=backend or "local",
                )
            return JSONResponse(payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Graph snapshot failed for workspace=%s: %s", workspace, exc
            )
            raise HTTPException(500, f"Graph snapshot failed: {exc}") from exc

