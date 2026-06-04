"""One-time backfill: stamp entity-type Neo4j labels on existing workspace nodes.

Nodes written by LightRAG rc3 have ``n.entity_type`` as a property but NOT as
a Neo4j label, so Neo4j Browser only shows the workspace label.  This script
reads the ``entity_type`` property from every node and calls SET n:`{type}` for
each distinct value.

Usage (from repo root, venv activated)::

    python tools/backfill_neo4j_entity_labels.py --workspace swa_tas2
    python tools/backfill_neo4j_entity_labels.py --workspace swa_tas2 --dry-run

Environment variables read from .env:
    NEO4J_URI     — default bolt://localhost:7687
    NEO4J_USER    — default neo4j
    NEO4J_PASSWORD
    NEO4J_DATABASE — default neo4j
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Load .env before importing anything that reads env at import time.
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
)
logger = logging.getLogger(__name__)


async def run(workspace: str, *, dry_run: bool) -> None:
    try:
        from neo4j import AsyncGraphDatabase
    except ImportError:
        logger.error("neo4j driver not found — run `uv sync` to ensure dev deps are installed")
        sys.exit(1)

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    if not password:
        logger.error("NEO4J_PASSWORD not set in .env")
        sys.exit(1)

    async with AsyncGraphDatabase.driver(uri, auth=(user, password)) as driver:
        # --- discover distinct entity types in the workspace ---
        async with driver.session(database=database, default_access_mode="READ") as session:
            result = await session.run(
                f"MATCH (n:`{workspace}`) WHERE n.entity_type IS NOT NULL "
                f"RETURN collect(DISTINCT n.entity_type) AS types, count(n) AS total"
            )
            record = await result.single()
            await result.consume()

        if not record:
            logger.info("Workspace '%s' not found or empty — nothing to do", workspace)
            return

        total_nodes: int = record["total"]
        types: list[str] = record["types"]

        logger.info(
            "Workspace '%s': %d node(s), %d distinct entity_type value(s)",
            workspace,
            total_nodes,
            len(types),
        )
        for t in sorted(types):
            logger.info("  %s", t)

        if dry_run:
            logger.info("Dry run — no labels written")
            return

        # --- stamp labels per type ---
        from src.server.neo4j_entity_label_patch import _sanitize_label

        grand_total = 0
        for raw_type in sorted(types):
            entity_type = _sanitize_label(raw_type)
            async with driver.session(database=database) as session:
                result = await session.run(
                    f"MATCH (n:`{workspace}`) WHERE n.entity_type = $et "
                    f"SET n:`{entity_type}` "
                    f"RETURN count(n) AS stamped",
                    et=raw_type,
                )
                record = await result.single()
                await result.consume()
                stamped: int = record["stamped"] if record else 0
                logger.info("  %-30s  stamped %d node(s)", entity_type, stamped)
                grand_total += stamped

        logger.info(
            "Done — %d node(s) in workspace '%s' now have entity-type labels",
            grand_total,
            workspace,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        required=True,
        help="Neo4j workspace label to backfill (e.g. swa_tas2)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be stamped without writing any labels",
    )
    args = parser.parse_args()
    asyncio.run(run(args.workspace, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
