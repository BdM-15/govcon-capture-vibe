"""
Patch vdb_entities.json metadata from Neo4j — no re-ingest, no re-embed.

Reads entity_type / description / source_id from the workspace graph and mirrors
them into the LightRAG entity VDB JSON in-place. Embedding vectors are untouched.

Usage:
    python tools/sync_vdb_entity_metadata.py mcpp_rfp
    python tools/sync_vdb_entity_metadata.py --all
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("sync_vdb_entity_metadata")


def list_workspaces() -> list[str]:
    storage = REPO_ROOT / "rag_storage"
    if not storage.is_dir():
        return []
    return sorted(
        p.name
        for p in storage.iterdir()
        if p.is_dir() and (p / "vdb_entities.json").is_file()
    )


def sync_one(workspace: str) -> dict[str, int]:
    os.environ["WORKSPACE"] = workspace
    from src.core import config as core_config

    core_config.reset_settings()

    from src.core.neo4j_config import get_neo4j_connection_config
    from src.inference.neo4j_graph_io import Neo4jGraphIO
    from src.inference.semantic_post_process_support import (
        sync_workspace_entity_metadata_from_neo4j,
    )

    config = get_neo4j_connection_config(database_fallback=workspace)
    if not config.enabled:
        raise RuntimeError(
            f"Neo4j not enabled (GRAPH_STORAGE={config.graph_storage!r}); cannot sync metadata"
        )

    rag_path = str(REPO_ROOT / "rag_storage" / workspace)
    io = Neo4jGraphIO()
    try:
        if io.workspace != workspace:
            logger.warning(
                "Neo4j workspace label %s differs from requested %s — using %s",
                io.workspace,
                workspace,
                io.workspace,
            )
        entities = io.get_all_entities()
        stats = sync_workspace_entity_metadata_from_neo4j(
            rag_storage_path=rag_path,
            entity_records=entities,
        )
    finally:
        io.close()

    logger.info(
        "%s: patched %s / %s VDB rows from %s Neo4j entities",
        workspace,
        stats["rows_updated"],
        stats["vdb_rows"],
        stats["neo4j_entities"],
    )
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspaces", nargs="*", help="Workspace folder under rag_storage/")
    parser.add_argument("--all", action="store_true", help="Sync every workspace with vdb_entities.json")
    args = parser.parse_args()

    if args.all:
        workspaces = list_workspaces()
        if not workspaces:
            logger.error("No workspaces with vdb_entities.json found")
            return 2
    elif args.workspaces:
        workspaces = args.workspaces
    else:
        parser.error("Provide workspace name(s) or --all")

    failures = 0
    for workspace in workspaces:
        try:
            sync_one(workspace)
        except Exception as exc:
            failures += 1
            logger.exception("%s: metadata sync failed: %s", workspace, exc)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())