"""Workspace and graph-explorer feature routes for Project Theseus UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.core import reset_settings
from src.core.neo4j_config import get_neo4j_connection_config
from src.inference.neo4j_graph_io import Neo4jGraphIO

logger = logging.getLogger(__name__)

_COUNT_CACHE: dict[tuple[str, int, int], int] = {}
_SAFE_WS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
GRAPH_HARD_CAP = 5000
GRAPH_DEFAULT = 2000
SYSTEM_LABELS = {"__Entity__", "__Relation__", "__Community__", "base", "DELETED"}
_NON_WORKSPACE_LABELS = {"UNKNOWN", "table", "image", "equation", "list", "figure"}
_INPUTS_RESERVED = {"uploaded", "__enqueued__"}
HEX_SUFFIX = re.compile(r"_[0-9a-f]{8}$", re.IGNORECASE)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class WorkspaceSwitch(BaseModel):
    """Body for POST /api/ui/workspaces/switch."""

    name: str = Field(..., min_length=1, max_length=64)
    create: bool = Field(default=False, description="Create folder if it does not exist.")


class WorkspaceDeleteScope(BaseModel):
    """Which buckets of workspace to delete. At least one must be true."""

    neo4j: bool = Field(default=False, description="Delete workspace Neo4j subgraph.")
    rag_storage: bool = Field(default=False, description="Delete rag_storage/<ws>/.")
    inputs: bool = Field(default=False, description="Delete inputs/<ws>/ source docs.")


class WipeAllScope(BaseModel):
    """Clean-slate wipe. Requires literal confirmation phrase."""

    neo4j: bool = Field(default=False)
    rag_storage: bool = Field(default=False)
    inputs: bool = Field(default=False)
    confirm: str = Field(..., description="Must equal 'DELETE ALL'.")


def safe_count_json_keys(path: Path) -> int:
    """Count records in LightRAG storage JSON file, returning 0 on errors."""
    try:
        if not path.exists():
            return 0
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        cached = _COUNT_CACHE.get(key)
        if cached is not None:
            return cached
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            inner = data.get("data")
            count = len(inner) if isinstance(inner, list) else len(data)
        elif isinstance(data, list):
            count = len(data)
        else:
            count = 0
        for old_key in [old_key for old_key in _COUNT_CACHE if old_key[0] == str(path)]:
            _COUNT_CACHE.pop(old_key, None)
        _COUNT_CACHE[key] = count
        return count
    except Exception:  # noqa: BLE001
        return 0


def _rag_storage_root() -> Path:
    """Parent rag_storage dir (WORKING_DIR env var)."""
    working_dir = os.getenv("WORKING_DIR", "./rag_storage")
    return Path(working_dir).resolve()


def _inputs_root() -> Path:
    """Parent inputs dir (sibling of rag_storage)."""
    return (_PROJECT_ROOT / "inputs").resolve()


def _folder_size_mb(path: Path) -> float:
    """Recursively sum file sizes in path, return MB."""
    total = sum(entry.stat().st_size for entry in path.rglob("*") if entry.is_file())
    return round(total / 1024 / 1024, 1)


def _entity_type_labels(session) -> set[str]:
    """Return label names that are entity types, not workspaces."""
    rec = session.run(
        "MATCH (n) WHERE n.entity_type IS NOT NULL "
        "RETURN collect(DISTINCT toLower(n.entity_type)) as types"
    ).single()
    types = set(rec["types"] if rec else [])
    try:
        from src.ontology.schema import VALID_ENTITY_TYPES  # type: ignore

        types |= {entity_type.lower() for entity_type in VALID_ENTITY_TYPES}
    except Exception:
        pass
    return types


def _neo4j_workspaces(neo4j_io: Neo4jGraphIO) -> dict[str, int]:
    """Return true workspace labels and node counts."""
    with neo4j_io.driver.session(database=neo4j_io.database) as session:
        entity_labels = _entity_type_labels(session)
        record = session.run(
            "CALL db.labels() YIELD label RETURN collect(label) as labels"
        ).single()
        labels = record["labels"] if record else []

        counts: dict[str, int] = {}
        for label in labels:
            if label in SYSTEM_LABELS:
                continue
            if label.lower() in entity_labels:
                continue
            if label in _NON_WORKSPACE_LABELS or label.startswith("#"):
                continue
            rec = session.run(f"MATCH (n:`{label}`) RETURN count(n) as c").single()
            count = rec["c"] if rec else 0
            if count > 0:
                counts[label] = count
    return counts


def _storage_workspaces(rag_root: Path) -> dict[str, float]:
    """Return workspace names and folder sizes under rag_storage."""
    result: dict[str, float] = {}
    if not rag_root.exists():
        return result
    for entry in rag_root.iterdir():
        if entry.is_dir() and not HEX_SUFFIX.search(entry.name):
            result[entry.name] = _folder_size_mb(entry)
    return result


def _inputs_workspaces(inputs_root: Path) -> dict[str, tuple[int, float]]:
    """Return workspace names and input-file counts/sizes under inputs/."""
    result: dict[str, tuple[int, float]] = {}
    if not inputs_root.exists():
        return result
    for entry in inputs_root.iterdir():
        if not entry.is_dir() or entry.name in _INPUTS_RESERVED:
            continue
        files = [child for child in entry.iterdir() if child.is_file()]
        if not files:
            result[entry.name] = (0, 0.0)
            continue
        total_bytes = sum(child.stat().st_size for child in files)
        result[entry.name] = (len(files), round(total_bytes / 1024 / 1024, 1))
    return result


def _delete_neo4j_workspace(neo4j_io: Neo4jGraphIO, workspace_name: str) -> int:
    """Delete all Neo4j nodes for one workspace label."""
    with neo4j_io.driver.session(database=neo4j_io.database) as session:
        rec = session.run(f"MATCH (n:`{workspace_name}`) RETURN count(n) as c").single()
        count = rec["c"] if rec else 0
        if count > 0:
            session.execute_write(
                lambda tx: tx.run(
                    f"MATCH (n:`{workspace_name}`) DETACH DELETE n"
                ).consume()
            )
    return count


def _delete_storage_workspace(workspace_name: str, rag_root: Path) -> bool:
    """Delete rag_storage/<workspace>, handling Windows log-file locks."""
    import tempfile

    ws_path = rag_root / workspace_name
    if not ws_path.exists():
        return False

    locked_files: list[Path] = []

    def _on_exc(func, path, exc):
        if isinstance(exc, (PermissionError, OSError)):
            if Path(path).is_file():
                locked_files.append(Path(path))
        else:
            raise exc

    try:
        shutil.rmtree(ws_path, onexc=_on_exc)
    except TypeError:
        def _on_err(func, path, exc_info):
            exc = exc_info[1]
            if isinstance(exc, (PermissionError, OSError)):
                if Path(path).is_file():
                    locked_files.append(Path(path))
            else:
                raise exc

        shutil.rmtree(ws_path, onerror=_on_err)

    if not locked_files:
        return True

    tmp_dir = Path(tempfile.gettempdir())
    still_locked: list[Path] = []
    for file_path in locked_files:
        if not file_path.exists():
            continue
        dest = tmp_dir / f"{workspace_name}_{file_path.name}"
        try:
            file_path.rename(dest)
        except OSError:
            still_locked.append(file_path)

    for dirpath in sorted(ws_path.rglob("*"), reverse=True):
        if dirpath.is_dir():
            try:
                dirpath.rmdir()
            except OSError:
                pass
    try:
        ws_path.rmdir()
    except OSError:
        pass

    if still_locked:
        print(
            f"\n  ⚠️  {len(still_locked)} file(s) could not be removed (server lock - restart server and retry):"
        )
        for file_path in still_locked:
            try:
                print(f"     - {file_path.relative_to(rag_root)}")
            except ValueError:
                print(f"     - {file_path}")

    return True


def _delete_inputs_workspace(workspace_name: str, inputs_root: Path) -> tuple[int, float]:
    """Delete files inside inputs/<workspace>, keeping dir if possible."""
    ws_path = inputs_root / workspace_name
    if not ws_path.exists() or not ws_path.is_dir():
        return (0, 0.0)

    deleted = 0
    bytes_freed = 0
    for entry in ws_path.iterdir():
        try:
            if entry.is_file():
                bytes_freed += entry.stat().st_size
                entry.unlink()
                deleted += 1
            elif entry.is_dir():
                bytes_freed += sum(child.stat().st_size for child in entry.rglob("*") if child.is_file())
                shutil.rmtree(entry)
        except OSError as exc:
            print(f"  ⚠️  Could not delete {entry.name}: {exc}")
    return (deleted, round(bytes_freed / 1024 / 1024, 1))


class WorkspaceMaintenance:
    """Deep module for workspace inventory and delete flows."""

    def __init__(
        self,
        *,
        graph_io_factory: Callable[[], Neo4jGraphIO] = Neo4jGraphIO,
    ) -> None:
        self._graph_io_factory = graph_io_factory

    def discover_workspaces(self, working_dir: Path) -> list[dict[str, Any]]:
        """List candidate workspaces under working directory."""
        if not working_dir.exists():
            return []
        signature_files = (
            "kv_store_doc_status.json",
            "vdb_entities.json",
            "vdb_chunks.json",
        )
        workspaces: list[dict[str, Any]] = []
        for child in sorted(working_dir.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue
            has_data = any((child / filename).exists() for filename in signature_files)
            workspaces.append(
                {
                    "name": child.name,
                    "has_data": has_data,
                    "documents": safe_count_json_keys(child / "kv_store_doc_status.json"),
                    "entities": safe_count_json_keys(child / "vdb_entities.json"),
                    "chats": sum(1 for _ in (child / "chats").glob("*.json"))
                    if (child / "chats").exists()
                    else 0,
                }
            )
        return workspaces

    def workspace_inventory(self, *, active_workspace: str, graph_storage: str) -> dict[str, Any]:
        """Combine rag_storage, Neo4j, and inputs views into one table."""
        rag_root = _rag_storage_root()
        inputs_root = _inputs_root()
        storage_ws = _storage_workspaces(rag_root)
        inputs_ws = _inputs_workspaces(inputs_root)

        neo4j_ws: dict[str, int] = {}
        backend = (graph_storage or "").lower()
        if "neo4j" in backend:
            try:
                io = self._graph_io_factory()
                try:
                    neo4j_ws = _neo4j_workspaces(io)
                finally:
                    io.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Neo4j inventory failed: %s", exc)

        all_names = sorted(set(neo4j_ws) | set(storage_ws) | set(inputs_ws))
        rows: list[dict[str, Any]] = []
        for name in all_names:
            inputs = inputs_ws.get(name)
            rows.append(
                {
                    "name": name,
                    "is_active": name == active_workspace,
                    "neo4j_nodes": neo4j_ws.get(name, 0),
                    "storage_mb": storage_ws.get(name),
                    "inputs_files": inputs[0] if inputs else 0,
                    "inputs_mb": inputs[1] if inputs else 0.0,
                }
            )
        return {
            "active": active_workspace,
            "rag_storage_root": str(rag_root),
            "inputs_root": str(inputs_root),
            "neo4j_available": "neo4j" in backend,
            "workspaces": rows,
        }

    def delete_workspace(self, name: str, scope: Any, *, graph_storage: str) -> dict[str, Any]:
        """Delete one workspace across selected storage buckets."""
        result: dict[str, Any] = {"workspace": name, "deleted": {}}

        if getattr(scope, "neo4j", False):
            backend = (graph_storage or "").lower()
            if "neo4j" in backend:
                try:
                    io = self._graph_io_factory()
                    try:
                        nodes = _delete_neo4j_workspace(io, name)
                        result["deleted"]["neo4j_nodes"] = nodes
                    finally:
                        io.close()
                except Exception as exc:  # noqa: BLE001
                    result["deleted"]["neo4j_error"] = str(exc)
            else:
                result["deleted"]["neo4j_skipped"] = "backend is not Neo4j"

        if getattr(scope, "rag_storage", False):
            try:
                existed = _delete_storage_workspace(name, _rag_storage_root())
                result["deleted"]["rag_storage"] = existed
            except Exception as exc:  # noqa: BLE001
                result["deleted"]["rag_storage_error"] = str(exc)

        if getattr(scope, "inputs", False):
            try:
                count, mb = _delete_inputs_workspace(name, _inputs_root())
                workspace_inputs = _inputs_root() / name
                if (
                    workspace_inputs.exists()
                    and workspace_inputs.is_dir()
                    and not any(workspace_inputs.iterdir())
                ):
                    try:
                        workspace_inputs.rmdir()
                    except OSError:
                        pass
                result["deleted"]["inputs_files"] = count
                result["deleted"]["inputs_mb"] = mb
            except Exception as exc:  # noqa: BLE001
                result["deleted"]["inputs_error"] = str(exc)

        return result

    def ensure_active_storage_workspace(self, active_workspace: str) -> None:
        """Ensure active rag_storage workspace exists."""
        (_rag_storage_root() / active_workspace).mkdir(parents=True, exist_ok=True)


DEFAULT_WORKSPACE_MAINTENANCE = WorkspaceMaintenance()


def discover_workspaces(working_dir: Path) -> list[dict[str, Any]]:
    """List candidate workspaces under configured working directory."""
    return DEFAULT_WORKSPACE_MAINTENANCE.discover_workspaces(working_dir)


def set_env_var(key: str, value: str) -> None:
    """Update or append KEY=value in project .env file."""
    env_path = Path.cwd() / ".env"
    lines: list[str] = []
    found = False
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            stripped = raw.lstrip()
            if stripped.startswith(f"{key}=") and not stripped.startswith("#"):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(raw)
    if not found:
        lines.append(f"{key}={value}")
    tmp = env_path.with_suffix(".env.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(env_path)
    os.environ[key] = value
    reset_settings()


def self_restart() -> None:
    """Re-exec current python process with same argv."""
    logger.warning("Re-execing process: %s %s", sys.executable, sys.argv)
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as exc:  # pragma: no cover
        logger.exception("Self-restart failed: %s", exc)
        os._exit(1)


def workspace_inventory(*, active_workspace: str, graph_storage: str) -> dict[str, Any]:
    """Combine rag_storage, Neo4j, and inputs views into one table."""
    return DEFAULT_WORKSPACE_MAINTENANCE.workspace_inventory(
        active_workspace=active_workspace,
        graph_storage=graph_storage,
    )


def delete_workspace_sync(
    name: str,
    scope: WorkspaceDeleteScope,
    *,
    graph_storage: str,
) -> dict[str, Any]:
    """Delete one workspace's selected storage buckets."""
    return DEFAULT_WORKSPACE_MAINTENANCE.delete_workspace(
        name,
        scope,
        graph_storage=graph_storage,
    )


def ensure_active_storage_workspace(active_workspace: str) -> None:
    """Ensure active rag_storage workspace exists after clean-slate wipe."""
    DEFAULT_WORKSPACE_MAINTENANCE.ensure_active_storage_workspace(active_workspace)


def wipe_all_workspaces_sync(
    scope: WipeAllScope,
    *,
    active_workspace: str,
    graph_storage: str,
    inventory_func=workspace_inventory,
    delete_workspace_func=delete_workspace_sync,
    ensure_active_workspace: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Clean-slate wipe across every discovered workspace."""
    if ensure_active_workspace is None:
        ensure_active_workspace = ensure_active_storage_workspace

    inventory = inventory_func(
        active_workspace=active_workspace,
        graph_storage=graph_storage,
    )
    names = [row["name"] for row in inventory["workspaces"]]
    results = [
        delete_workspace_func(
            name,
            WorkspaceDeleteScope(
                neo4j=scope.neo4j,
                rag_storage=scope.rag_storage,
                inputs=scope.inputs,
            ),
            graph_storage=graph_storage,
        )
        for name in names
    ]
    try:
        ensure_active_workspace(active_workspace)
    except Exception:  # noqa: BLE001
        pass
    return {"deleted": results, "workspaces": len(results)}


def _chunk_ids_for_entity(entity_chunks_map: dict[str, Any], name: str) -> list[str]:
    chunk_ids = entity_chunks_map.get(name) or entity_chunks_map.get(name.strip('"')) or []
    if isinstance(chunk_ids, dict):
        return list(chunk_ids.keys())
    if isinstance(chunk_ids, list):
        return [str(chunk_id) for chunk_id in chunk_ids]
    return []


def load_entity_chunks(workspace_dir: Path, name: str, limit: int = 8) -> dict[str, Any]:
    """Return source text chunk previews that mention entity."""
    entity_chunks_path = workspace_dir / "kv_store_entity_chunks.json"
    text_chunks_path = workspace_dir / "kv_store_text_chunks.json"
    if not entity_chunks_path.exists() or not text_chunks_path.exists():
        return {"entity": name, "chunks": []}
    try:
        entity_chunks_map = json.loads(entity_chunks_path.read_text(encoding="utf-8"))
        text_chunks = json.loads(text_chunks_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed reading chunk stores: %s", exc)
        return {"entity": name, "chunks": []}
    if not isinstance(entity_chunks_map, dict) or not isinstance(text_chunks, dict):
        return {"entity": name, "chunks": []}

    chunks: list[dict[str, Any]] = []
    for chunk_id in _chunk_ids_for_entity(entity_chunks_map, name)[:limit]:
        chunk = text_chunks.get(chunk_id) or {}
        if not isinstance(chunk, dict):
            chunk = {}
        content = chunk.get("content") or chunk.get("text") or ""
        chunks.append(
            {
                "chunk_id": chunk_id,
                "file_path": chunk.get("file_path") or chunk.get("full_doc_id"),
                "chunk_order_index": chunk.get("chunk_order_index"),
                "snippet": content[:600] + ("…" if len(content) > 600 else ""),
            }
        )
    return {"entity": name, "chunks": chunks}


def register_entity_chunk_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
) -> None:
    """Register KG explorer entity drill-down endpoints."""

    @app.get("/api/ui/entity/{name}/chunks", tags=["theseus-ui"])
    async def entity_chunks(name: str, limit: int = 8) -> JSONResponse:
        """Return source text chunks that mention entity."""
        return JSONResponse(load_entity_chunks(workspace_dir(), name, limit=limit))


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


def load_graph_networkx(
    workspace: str,
    max_nodes: int,
    entity_type: str | None,
    *,
    working_dir: Path,
) -> dict[str, Any]:
    """Read graph_chunk_entity_relation.graphml and build UI payload."""
    import networkx as nx

    graphml = working_dir / workspace / "graph_chunk_entity_relation.graphml"
    if not graphml.exists():
        return {
            "backend": "networkx",
            "workspace": workspace,
            "nodes": [],
            "edges": [],
            "total_nodes": 0,
            "returned_nodes": 0,
            "returned_edges": 0,
            "is_truncated": False,
        }

    graph = nx.read_graphml(str(graphml))
    if entity_type:
        keep = [
            node
            for node, data in graph.nodes(data=True)
            if str(data.get("entity_type", "")).lower() == entity_type.lower()
        ]
        graph = graph.subgraph(keep).copy()

    total = graph.number_of_nodes()
    if total > max_nodes:
        top = sorted(graph.degree(), key=lambda item: item[1], reverse=True)[:max_nodes]
        keep = [node for node, _ in top]
        graph = graph.subgraph(keep).copy()

    nodes_payload: list[dict[str, Any]] = []
    for node, data in graph.nodes(data=True):
        props = json_safe(dict(data))
        nodes_payload.append(
            {
                "id": str(node),
                "labels": [str(props.get("entity_id", node))],
                "properties": {**props, "_degree": int(graph.degree(node))},
            }
        )

    edges_payload: list[dict[str, Any]] = []
    for index, (source, target, data) in enumerate(graph.edges(data=True)):
        props = json_safe(dict(data))
        relationship_type = (
            props.pop("relationship_type", None)
            or props.get("keywords")
            or "RELATED_TO"
        )
        edges_payload.append(
            {
                "id": str(index),
                "source": str(source),
                "target": str(target),
                "type": str(relationship_type),
                "properties": props,
            }
        )

    return {
        "backend": "networkx",
        "workspace": workspace,
        "nodes": nodes_payload,
        "edges": edges_payload,
        "total_nodes": int(total),
        "returned_nodes": len(nodes_payload),
        "returned_edges": len(edges_payload),
        "is_truncated": total > len(nodes_payload),
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
                payload = load_graph_networkx(
                    workspace,
                    cap,
                    entity_type,
                    working_dir=working_dir(),
                )
            return JSONResponse(payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Graph snapshot failed for workspace=%s: %s", workspace, exc
            )
            raise HTTPException(500, f"Graph snapshot failed: {exc}") from exc


def now_iso() -> str:
    """Return compact UTC timestamp for UI rollups."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_vdb(workspace_dir: Path, name: str) -> list[dict[str, Any]]:
    """Load vdb_*.json file data array, returning [] on failure."""
    path = workspace_dir / name
    try:
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw.get("data") or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed reading %s: %s", path, exc)
        return []


def split_keywords(value: Any) -> list[str]:
    """Relationship keywords can be list or comma/space-joined string."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if item]
    return [
        token.strip().upper()
        for token in re.split(r"[,\s]+", str(value))
        if token.strip()
    ]


def compute_intel(
    workspace_dir: Path,
    *,
    generated_at: Callable[[], str] = now_iso,
) -> dict[str, Any]:
    """Build RFP intelligence rollup from workspace VDB JSON stores."""
    entities = load_vdb(workspace_dir, "vdb_entities.json")
    relations = load_vdb(workspace_dir, "vdb_relationships.json")

    by_name: dict[str, dict[str, Any]] = {}
    for entity in entities:
        name = (
            entity.get("entity_name")
            or entity.get("entity_id")
            or entity.get("__id__")
        )
        if not name:
            continue
        by_name[str(name).strip()] = entity

    buckets: dict[str, list[str]] = {}
    for name, entity in by_name.items():
        entity_type = (entity.get("entity_type") or "concept").lower()
        buckets.setdefault(entity_type, []).append(name)

    out_edges: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    in_edges: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for relation in relations:
        source = relation.get("src_id")
        target = relation.get("tgt_id")
        if not source or not target:
            continue
        types = split_keywords(
            relation.get("keywords") or relation.get("relationship_type")
        )
        for relationship_type in types:
            out_edges.setdefault(source, []).append((relationship_type, target, relation))
            in_edges.setdefault(target, []).append((relationship_type, source, relation))

    def outgoing(name: str, relationship_type: str) -> list[str]:
        return [
            target
            for edge_type, target, _ in out_edges.get(name, [])
            if edge_type == relationship_type
        ]

    def incoming(name: str, relationship_type: str) -> list[str]:
        return [
            source
            for edge_type, source, _ in in_edges.get(name, [])
            if edge_type == relationship_type
        ]

    def summarize(name: str, max_chars: int = 110) -> dict[str, Any]:
        entity = by_name.get(name) or {}
        description = (
            entity.get("description") or entity.get("content") or ""
        ).strip().replace("\n", " ")
        return {
            "id": name,
            "type": (entity.get("entity_type") or "concept").lower(),
            "description": (
                description[:max_chars] + "…"
                if len(description) > max_chars
                else description
            ),
        }

    lm_rows: list[dict[str, Any]] = []
    for instruction in sorted(buckets.get("proposal_instruction", [])):
        guided = sorted(
            set(
                outgoing(instruction, "GUIDES")
                + outgoing(instruction, "EVALUATED_BY")
            )
        )
        lm_rows.append(
            {
                "instruction": summarize(instruction),
                "factors": [summarize(factor) for factor in guided],
                "covered": bool(guided),
            }
        )

    factor_names = sorted(
        set(buckets.get("evaluation_factor", []) + buckets.get("subfactor", []))
    )
    factor_rows: list[dict[str, Any]] = []
    for factor in factor_names:
        guides = sorted(
            set(incoming(factor, "GUIDES") + incoming(factor, "EVALUATED_BY"))
        )
        factor_rows.append(
            {
                "factor": summarize(factor),
                "instructions": [summarize(instruction) for instruction in guides],
                "covered": bool(guides),
            }
        )

    trace_rows: list[dict[str, Any]] = []
    for requirement in sorted(buckets.get("requirement", [])):
        deliverables = sorted(set(outgoing(requirement, "SATISFIED_BY")))
        if not deliverables:
            trace_rows.append(
                {
                    "requirement": summarize(requirement),
                    "deliverables": [],
                    "standards": [],
                    "metrics": [],
                    "complete": False,
                }
            )
            continue
        for deliverable in deliverables:
            standards = sorted(set(outgoing(deliverable, "MEASURED_BY")))
            metrics = sorted(
                set(
                    outgoing(deliverable, "TRACKED_BY")
                    + outgoing(deliverable, "QUANTIFIES")
                )
            )
            trace_rows.append(
                {
                    "requirement": summarize(requirement),
                    "deliverables": [summarize(deliverable)],
                    "standards": [summarize(standard) for standard in standards],
                    "metrics": [summarize(metric) for metric in metrics],
                    "complete": bool(standards or metrics),
                }
            )

    coverage_rows: list[dict[str, Any]] = []
    for factor in sorted(buckets.get("evaluation_factor", [])):
        subfactors = sorted(
            set(outgoing(factor, "HAS_SUBFACTOR") + outgoing(factor, "CHILD_OF"))
        )
        instructions = sorted(set(incoming(factor, "GUIDES")))
        evidence: set[str] = set()
        for relationship_type in ("SUPPORTS", "EVIDENCES", "ADDRESSES"):
            evidence.update(incoming(factor, relationship_type))
        score = (
            (1 if instructions else 0)
            + (1 if subfactors else 0)
            + (1 if evidence else 0)
        )
        coverage_rows.append(
            {
                "factor": summarize(factor),
                "subfactor_count": len(subfactors),
                "instruction_count": len(instructions),
                "evidence_count": len(evidence),
                "score": score,
            }
        )

    gaps_req = [
        summarize(requirement)
        for requirement in sorted(buckets.get("requirement", []))
        if not outgoing(requirement, "SATISFIED_BY")
    ]
    gaps_factor = [
        summarize(factor)
        for factor in factor_names
        if not (incoming(factor, "GUIDES") or incoming(factor, "EVALUATED_BY"))
    ]
    gaps_deliverable = [
        summarize(deliverable)
        for deliverable in sorted(buckets.get("deliverable", []))
        if not (
            outgoing(deliverable, "MEASURED_BY")
            or outgoing(deliverable, "TRACKED_BY")
        )
    ]

    return {
        "generated_at": generated_at(),
        "totals": {
            "entities": len(by_name),
            "relationships": len(relations),
            "by_type": {
                key: len(value)
                for key, value in sorted(
                    buckets.items(),
                    key=lambda item: -len(item[1]),
                )
            },
        },
        "lm_matrix": {
            "instructions": lm_rows,
            "factors": factor_rows,
        },
        "traceability": trace_rows,
        "coverage": coverage_rows,
        "gaps": {
            "requirements_no_satisfaction": gaps_req,
            "factors_no_instruction": gaps_factor,
            "deliverables_no_measure": gaps_deliverable,
        },
    }


def register_intelligence_routes(
    app: FastAPI,
    *,
    workspace_dir: Callable[[], Path],
) -> None:
    """Register RFP intelligence routes for Theseus UI."""

    @app.get("/api/ui/intel/summary", tags=["theseus-ui"])
    async def intel_summary() -> JSONResponse:
        """Compute L↔M matrix, traceability chains, factor coverage, and gaps."""
        return JSONResponse(compute_intel(workspace_dir()))


def register_workspace_ui_routes(
    app: FastAPI,
    *,
    workspace_name: Callable[[], str],
    working_dir: Callable[[], Path],
    graph_storage: Callable[[], str],
    set_env_var_func: Callable[[str, str], None] = set_env_var,
    schedule_restart: Callable[[float], None] | None = None,
    inventory_func: Callable[..., dict[str, Any]] = workspace_inventory,
    delete_workspace_func: Callable[..., dict[str, Any]] = delete_workspace_sync,
    ensure_active_workspace: Callable[[str], None] = ensure_active_storage_workspace,
) -> None:
    """Register workspace list, switch, inventory, delete, wipe, and restart routes."""

    def _schedule_restart(delay: float) -> None:
        if schedule_restart is not None:
            schedule_restart(delay)
        else:
            asyncio.get_event_loop().call_later(delay, self_restart)

    @app.get("/api/ui/workspaces", tags=["theseus-ui"])
    async def list_workspaces() -> JSONResponse:
        """List discovered workspace directories under rag_storage/."""
        return JSONResponse(
            {
                "active": workspace_name(),
                "workspaces": discover_workspaces(working_dir()),
            }
        )

    @app.post("/api/ui/workspaces/switch", tags=["theseus-ui"])
    async def switch_workspace(payload: WorkspaceSwitch) -> JSONResponse:
        """Persist WORKSPACE=<name> and schedule graceful restart."""
        name = payload.name.strip()
        if not _SAFE_WS.match(name):
            raise HTTPException(400, "Invalid workspace name (use alphanumerics, _, -)")
        existing = {workspace["name"] for workspace in discover_workspaces(working_dir())}
        if not payload.create and name not in existing:
            raise HTTPException(404, f"Workspace '{name}' does not exist")
        working_dir().mkdir(parents=True, exist_ok=True)
        (working_dir() / name).mkdir(parents=True, exist_ok=True)
        try:
            set_env_var_func("WORKSPACE", name)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, f"Failed updating .env: {exc}") from exc
        _schedule_restart(0.75)
        logger.warning("Workspace switch requested -> '%s'. Restarting server...", name)
        return JSONResponse(
            {
                "status": "restarting",
                "workspace": name,
                "message": "Server is restarting. The UI will reconnect automatically.",
            }
        )

    @app.get("/api/ui/workspaces/inventory", tags=["theseus-ui"])
    async def workspaces_inventory() -> JSONResponse:
        """Per-workspace inventory: Neo4j node count, rag_storage size, inputs files."""
        result = await asyncio.to_thread(
            inventory_func,
            active_workspace=workspace_name(),
            graph_storage=graph_storage(),
        )
        return JSONResponse(result)

    @app.post("/api/ui/workspaces/{name}/delete", tags=["theseus-ui"])
    async def delete_workspace(name: str, scope: WorkspaceDeleteScope) -> JSONResponse:
        """Delete one workspace's selected buckets."""
        if not _SAFE_WS.match(name):
            raise HTTPException(400, "Invalid workspace name (use alphanumerics, _, -)")
        if not (scope.neo4j or scope.rag_storage or scope.inputs):
            raise HTTPException(
                400,
                "At least one scope (neo4j/rag_storage/inputs) must be true.",
            )
        if name == workspace_name():
            raise HTTPException(
                409,
                "Cannot delete the active workspace. Switch to another workspace first.",
            )
        logger.warning(
            "Deleting workspace '%s' (neo4j=%s, rag_storage=%s, inputs=%s)",
            name,
            scope.neo4j,
            scope.rag_storage,
            scope.inputs,
        )
        result = await asyncio.to_thread(
            delete_workspace_func,
            name,
            scope,
            graph_storage=graph_storage(),
        )
        return JSONResponse(result)

    @app.post("/api/ui/workspaces/wipe-all", tags=["theseus-ui"])
    async def wipe_all_workspaces(scope: WipeAllScope) -> JSONResponse:
        """Clean-slate wipe across every workspace. Requires confirm='DELETE ALL'."""
        if scope.confirm != "DELETE ALL":
            raise HTTPException(400, "Confirmation phrase must equal 'DELETE ALL'.")
        if not (scope.neo4j or scope.rag_storage or scope.inputs):
            raise HTTPException(
                400,
                "At least one scope (neo4j/rag_storage/inputs) must be true.",
            )

        logger.warning(
            "Wipe all workspaces requested (neo4j=%s, rag_storage=%s, inputs=%s)",
            scope.neo4j,
            scope.rag_storage,
            scope.inputs,
        )
        result = await asyncio.to_thread(
            wipe_all_workspaces_sync,
            scope,
            active_workspace=workspace_name(),
            graph_storage=graph_storage(),
            inventory_func=inventory_func,
            delete_workspace_func=delete_workspace_func,
            ensure_active_workspace=ensure_active_workspace,
        )
        _schedule_restart(0.75)
        result["restarting"] = True
        return JSONResponse(result)

    @app.post("/api/ui/restart", tags=["theseus-ui"])
    async def restart_server() -> JSONResponse:
        """Schedule graceful self-restart of server process."""
        _schedule_restart(0.75)
        logger.warning("Manual restart requested via Settings page.")
        return JSONResponse(
            {
                "status": "restarting",
                "workspace": workspace_name(),
                "message": "Server is restarting. The UI will reconnect automatically.",
            }
        )


__all__ = [
    "WorkspaceMaintenance",
    "compute_intel",
    "delete_workspace_sync",
    "discover_workspaces",
    "json_safe",
    "load_entity_chunks",
    "load_graph_networkx",
    "load_graph_neo4j",
    "load_vdb",
    "now_iso",
    "register_entity_chunk_routes",
    "register_graph_routes",
    "register_intelligence_routes",
    "register_workspace_ui_routes",
    "safe_count_json_keys",
    "self_restart",
    "set_env_var",
    "split_keywords",
    "workspace_inventory",
    "wipe_all_workspaces_sync",
]