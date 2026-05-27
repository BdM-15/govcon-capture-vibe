"""
Rerun semantic post-processing on an existing workspace.

Reads entities/relationships already in Neo4j (no MinerU, no chunking, no
extraction LLM calls) and re-executes the 5-phase enhancement pipeline,
including Phase 4 inference (L↔M links, document structure, orphan resolution).

Usage:
    python tools/rerun_postprocessing.py <workspace_name> [<workspace_name> ...]
    python tools/rerun_postprocessing.py --all

Environment is loaded from .env. Neo4j must be reachable.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env BEFORE importing anything that reads settings at import time
load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rerun_postprocessing")


def list_workspaces() -> list[str]:
    storage = REPO_ROOT / "rag_storage"
    if not storage.is_dir():
        return []
    return sorted(
        p.name for p in storage.iterdir()
        if p.is_dir() and (p / "kv_store_full_entities.json").exists()
    )


async def rerun_one(workspace: str) -> dict:
    # Force the workspace via env BEFORE importing settings/modules that cache it
    os.environ["WORKSPACE"] = workspace

    # Reset cached settings so the new WORKSPACE takes effect
    from src.core import config as core_config
    core_config.reset_settings()

    # Initialize native LightRAG so VDB sync (Phase 5) can write back to LightRAG kv stores.
    # Without this, inferred relationships land in Neo4j only and the JSON kv stores
    # the UI reads stay stale. This call is async and does NOT trigger document processing.
    # NOTE: lightrag.api.config parses sys.argv at import time, so we shield it from our CLI args.
    saved_argv = sys.argv[:]
    sys.argv = [sys.argv[0]]
    try:
        from lightrag.api.config import global_args
        from src.theseus_server import initialize_theseus_rag_runtime
        from src.server.runtime_state import get_active_rag_instance

        if get_active_rag_instance() is None:
            logger.info("Initializing native LightRAG for VDB sync ...")
            await initialize_theseus_rag_runtime(global_args_obj=global_args)
    finally:
        sys.argv = saved_argv

    from src.inference.semantic_post_processor import enhance_knowledge_graph

    settings = core_config.get_settings()
    rag_path = str(REPO_ROOT / "rag_storage" / workspace)

    logger.info("")
    logger.info("=" * 80)
    logger.info(f"▶ RERUN POST-PROCESSING: workspace={workspace}")
    logger.info(f"  Neo4j workspace label: {settings.neo4j_workspace}")
    logger.info(f"  Storage path:          {rag_path}")
    logger.info("=" * 80)

    # llm_func is unused inside enhance_knowledge_graph (uses centralized client)
    async def _noop(prompt: str, system_prompt: str = "") -> str:  # pragma: no cover
        raise RuntimeError("llm_func should not be invoked; centralized client is used")

    result = await enhance_knowledge_graph(
        rag_storage_path=rag_path,
        llm_func=_noop,
        batch_size=50,
    )
    logger.info(f"✅ {workspace}: {result}")
    return result


async def main_async(workspaces: list[str]) -> int:
    failures = 0
    for ws in workspaces:
        try:
            await rerun_one(ws)
        except Exception as exc:
            failures += 1
            logger.exception(f"❌ {ws}: post-processing failed: {exc}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspaces", nargs="*", help="Workspace names under rag_storage/")
    parser.add_argument("--all", action="store_true", help="Rerun every workspace with extracted entities")
    args = parser.parse_args()

    if args.all:
        workspaces = list_workspaces()
        if not workspaces:
            logger.error("No workspaces with extracted entities found under rag_storage/")
            return 2
    elif args.workspaces:
        workspaces = args.workspaces
    else:
        parser.print_help()
        return 2

    logger.info(f"Workspaces to rerun: {workspaces}")
    return asyncio.run(main_async(workspaces))


if __name__ == "__main__":
    sys.exit(main())
