"""
GovCon Domain Ontology Bootstrap

This module handles injecting the curated GovCon domain ontology into
a LightRAG workspace using the native `ainsert_custom_kg()` method.

Key Concepts:
------------
1. The ontology provides "evergreen" domain knowledge that exists BEFORE
   any RFP documents are uploaded. This enables:
   - Zero-document queries: "What is a Color Team review?"
   - Enhanced retrieval: Domain concepts connect to extracted entities
   - Evaluation grounding: Shipley methodology, FAR compliance patterns

2. Bootstrap happens ONCE per workspace, typically at creation time.
   The KG can be re-bootstrapped to update with new knowledge.

3. Uses the same `ainsert_custom_kg()` pattern proven in vdb_sync.py
   for syncing algorithm-discovered relationships.

Integration Points:
------------------
- Called from: src/server/initialization.py during workspace init
- CLI: tools/bootstrap_ontology.py for manual bootstrapping
- Config: AUTO_BOOTSTRAP_ONTOLOGY env var controls auto-bootstrap
"""

import logging
from src.utils.time_utils import now_local
from typing import TYPE_CHECKING

from src.ontology.bootstrap_support import (
    marker_path_for_workspace,
    prepare_custom_kg,
    read_bootstrap_marker,
    resolve_workspace_dir,
    write_bootstrap_marker,
)

from src.ontology.govcon_kg import (
    build_govcon_ontology_kg,
    get_ontology_stats,
    validate_ontology,
)

if TYPE_CHECKING:
    from lightrag import LightRAG

logger = logging.getLogger(__name__)


# Marker file to track bootstrap status
BOOTSTRAP_MARKER = ".ontology_bootstrap"


async def bootstrap_govcon_ontology(
    lightrag: "LightRAG",
    working_dir: str | None = None,
    force: bool = False
) -> dict:
    """
    Bootstrap the GovCon domain ontology into a LightRAG workspace.
    
    This injects curated entities, relationships, and knowledge chunks
    that provide domain context for queries and enhanced retrieval.
    
    Args:
        lightrag: Initialized LightRAG instance
        working_dir: Workspace directory (for marker file). If None, uses lightrag.working_dir
        force: If True, re-bootstrap even if already done
        
    Returns:
        dict: Bootstrap result with status, counts, timing
        
    Example:
        >>> from lightrag import LightRAG
        >>> rag = LightRAG(working_dir="./rag_storage/my_workspace")
        >>> result = await bootstrap_govcon_ontology(rag)
        >>> print(f"Bootstrapped {result['entities_added']} entities")
    """
    workspace_dir = resolve_workspace_dir(lightrag, working_dir)
    if not workspace_dir:
        logger.error("Cannot determine workspace directory for bootstrap")
        return {
            "status": "error",
            "error": "No working directory available"
        }
    
    marker_path = marker_path_for_workspace(workspace_dir, BOOTSTRAP_MARKER)
    
    # Check if already bootstrapped
    if not force:
        bootstrap_time = read_bootstrap_marker(marker_path)
    else:
        bootstrap_time = None
    if bootstrap_time is not None:
        logger.info(f"📚 Ontology already bootstrapped for {workspace_dir}")
        return {
            "status": "already_bootstrapped",
            "bootstrapped_at": bootstrap_time,
            "message": "Use force=True to re-bootstrap"
        }
    
    start_time = now_local()
    logger.info(f"🚀 Bootstrapping GovCon domain ontology into {workspace_dir}...")
    
    try:
        # Validate ontology first
        is_valid, errors = validate_ontology()
        if not is_valid:
            logger.warning(f"⚠️ Ontology validation found {len(errors)} issues (proceeding anyway)")
            for error in errors[:5]:
                logger.warning(f"   - {error}")
        
        # Get stats for logging
        stats = get_ontology_stats()
        logger.info(
            f"   📊 Loading: {stats['total_entities']} entities, "
            f"{stats['total_relationships']} relationships, "
            f"{stats['total_chunks']} chunks"
        )
        
        # Build the consolidated knowledge graph
        custom_kg = build_govcon_ontology_kg()
        
        source_label = "govcon_domain_ontology"
        custom_kg = prepare_custom_kg(custom_kg, source_label=source_label)
        
        # Inject into LightRAG using native async method
        logger.info("   📥 Injecting into LightRAG via ainsert_custom_kg()...")
        await lightrag.ainsert_custom_kg(custom_kg)
        
        # Write marker file
        end_time = now_local()
        duration = (end_time - start_time).total_seconds()
        
        write_bootstrap_marker(marker_path, end_time.isoformat())
        
        logger.info(f"✅ Ontology bootstrap complete in {duration:.2f}s")
        logger.info(f"   → Workspace now has domain context for enhanced queries")
        
        return {
            "status": "success",
            "workspace": workspace_dir,
            "entities_added": stats["total_entities"],
            "relationships_added": stats["total_relationships"],
            "chunks_added": stats["total_chunks"],
            "duration_seconds": duration,
            "bootstrapped_at": end_time.isoformat(),
        }
        
    except Exception as e:
        logger.error(f"❌ Ontology bootstrap failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "workspace": workspace_dir,
        }


async def check_bootstrap_status(working_dir: str) -> dict:
    """
    Check if a workspace has been bootstrapped with the ontology.
    
    Args:
        working_dir: Workspace directory to check
        
    Returns:
        dict: Status with bootstrapped flag and timestamp
    """
    marker_path = marker_path_for_workspace(working_dir, BOOTSTRAP_MARKER)
    bootstrap_time = read_bootstrap_marker(marker_path)
    if bootstrap_time is not None:
        return {
            "bootstrapped": True,
            "bootstrapped_at": bootstrap_time,
            "workspace": working_dir,
        }
    else:
        return {
            "bootstrapped": False,
            "workspace": working_dir,
        }


def clear_bootstrap_marker(working_dir: str) -> bool:
    """
    Clear the bootstrap marker to allow re-bootstrapping.
    
    Args:
        working_dir: Workspace directory
        
    Returns:
        bool: True if marker was cleared, False if didn't exist
    """
    import os

    marker_path = marker_path_for_workspace(working_dir, BOOTSTRAP_MARKER)

    if os.path.exists(marker_path):
        os.remove(marker_path)
        logger.info(f"🗑️ Cleared bootstrap marker for {working_dir}")
        return True
    return False


# =============================================================================
# Synchronous wrapper for non-async contexts
# =============================================================================

def bootstrap_govcon_ontology_sync(
    lightrag: "LightRAG",
    working_dir: str | None = None,
    force: bool = False
) -> dict:
    """
    Synchronous wrapper for bootstrap_govcon_ontology.
    
    Use this when calling from non-async code (e.g., initialization).
    """
    import asyncio
    
    # Check if we're in an event loop
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context, need to schedule
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                bootstrap_govcon_ontology(lightrag, working_dir, force)
            )
            return future.result()
    except RuntimeError:
        # No event loop, safe to use asyncio.run
        return asyncio.run(
            bootstrap_govcon_ontology(lightrag, working_dir, force)
        )


# =============================================================================
# CLI Support
# =============================================================================

if __name__ == "__main__":
    """
    Test bootstrap without full server:
        python -m src.ontology.bootstrap
    """
    import asyncio
    
    async def test_bootstrap():
        print("=" * 60)
        print("GovCon Domain Ontology Bootstrap Test")
        print("=" * 60)
        
        # Validate ontology
        print("\n🔍 Validating ontology...")
        is_valid, errors = validate_ontology()
        
        if is_valid:
            print("   ✅ Ontology valid!")
        else:
            print(f"   ⚠️ Found {len(errors)} issues:")
            for error in errors[:5]:
                print(f"      - {error}")
        
        # Show stats
        stats = get_ontology_stats()
        print(f"\n📊 Ontology ready with:")
        print(f"   - {stats['total_entities']} entities")
        print(f"   - {stats['total_relationships']} relationships")
        print(f"   - {stats['total_chunks']} chunks")
        
        print("\n✅ Bootstrap module ready")
        print("   Use: await bootstrap_govcon_ontology(lightrag_instance)")
    
    asyncio.run(test_bootstrap())
