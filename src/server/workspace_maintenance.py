"""Shared workspace maintenance helpers for UI routes and CLI tooling."""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Callable

from src.inference.neo4j_graph_io import Neo4jGraphIO
from src.server.storage_counts import safe_count_json_keys

logger = logging.getLogger(__name__)

SYSTEM_LABELS = {"__Entity__", "__Relation__", "__Community__", "base", "DELETED"}
_NON_WORKSPACE_LABELS = {"UNKNOWN", "table", "image", "equation", "list", "figure"}
_INPUTS_RESERVED = {"uploaded", "__enqueued__"}
HEX_SUFFIX = re.compile(r"_[0-9a-f]{8}$", re.IGNORECASE)
DIVIDER = "─" * 70
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _rag_storage_root() -> Path:
    """Parent rag_storage directory (WORKING_DIR env var)."""
    working_dir = os.getenv("WORKING_DIR", "./rag_storage")
    return Path(working_dir).resolve()


def _inputs_root() -> Path:
    """Parent inputs directory (sibling of rag_storage)."""
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
    """Return true workspace labels and their node counts."""
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


def _orphaned_mineru_dirs(rag_root: Path) -> list[Path]:
    """Legacy MinerU output dirs in rag_storage root."""
    if not rag_root.exists():
        return []
    return [entry for entry in rag_root.iterdir() if entry.is_dir() and HEX_SUFFIX.search(entry.name)]


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
    """Delete files inside inputs/<workspace>, keeping the directory if possible."""
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


def _handle_orphaned_dirs(
    rag_root: Path,
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> None:
    """Prompt to delete legacy orphaned MinerU output dirs in rag_storage root."""
    orphans = _orphaned_mineru_dirs(rag_root)
    if not orphans:
        return
    output_func(f"\n   🔍 Found {len(orphans)} legacy MinerU output dir(s) in rag_storage root:")
    for orphan in orphans:
        output_func(f"      - {orphan.name}")
    answer = input_func(
        f"\n   Delete these {len(orphans)} legacy orphaned dir(s)? (yes/no): "
    ).strip().lower()
    if answer in ("yes", "y"):
        for orphan in orphans:
            shutil.rmtree(orphan)
            output_func(f"   ✅ Deleted: {orphan.name}")
    else:
        output_func("   ⏭️  Skipped")


class WorkspaceMaintenance:
    """Deep module for workspace inventory and delete flows."""

    def __init__(
        self,
        *,
        graph_io_factory: Callable[[], Neo4jGraphIO] = Neo4jGraphIO,
    ) -> None:
        self._graph_io_factory = graph_io_factory

    def discover_workspaces(self, working_dir: Path) -> list[dict[str, Any]]:
        """List candidate workspaces under a working directory."""
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
        """Ensure the active rag_storage workspace exists."""
        (_rag_storage_root() / active_workspace).mkdir(parents=True, exist_ok=True)


DEFAULT_WORKSPACE_MAINTENANCE = WorkspaceMaintenance()
