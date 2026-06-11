"""
Semantic Post-Processing for Government Contracting RFPs
========================================================

Neo4j-native LLM-powered enhancements to the extracted knowledge graph:

1. **Entity Normalization**: Fix table/hash/unknown entity types
2. **Relationship Normalization**: Re-type generic RELATED_TO via entity-pair lookup
3. **Relationship Inference**: Infer missing semantic relationships using 3 algorithms
4. **VDB Synchronization**: Sync inferred relationships to LightRAG vector stores

Architecture (Issue #54 - Back to Basics):
- Entity extraction uses native LightRAG with the govcon ontology
- Pydantic validation is used for POST-PROCESSING only (InferredRelationship)
- No Pydantic validation during extraction - LightRAG handles it natively

Usage:
    from src.inference.semantic_post_processor import enhance_knowledge_graph
    
    stats = await enhance_knowledge_graph(
        rag_storage_path="path/to/rag_storage",
        llm_func=my_llm_function
    )
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict

from src.core import get_settings
from src.inference.neo4j_graph_io import Neo4jGraphIO, group_entities_by_type
from src.inference.algorithms import run_all_algorithms_parallel
from src.inference.semantic_post_process_support import (
    apply_entity_name_updates_to_vdb,
    build_post_processing_result,
    collect_relationship_retype_updates,
    heuristic_table_type_mapping as _heuristic_table_type_mapping,
    plan_entity_name_updates,
    plan_entity_type_updates,
    sync_entity_metadata_to_vdb,
)
from src.ontology.schema import VALID_ENTITY_TYPES

logger = logging.getLogger(__name__)

# Convert set to list for prompt generation
ALLOWED_TYPES = list(VALID_ENTITY_TYPES)


def get_semantic_post_processing_config():
    """Get semantic post-processing configuration from centralized settings."""
    settings = get_settings()
    return {
        'max_concurrent_llm_calls': settings.get_effective_post_processing_max_async(),
    }


# Legacy constants for backward compatibility (use get_semantic_post_processing_config() instead)
# These are evaluated at import time for modules that depend on them
_settings = get_settings()
MAX_CONCURRENT_LLM_CALLS = _settings.get_effective_post_processing_max_async()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTITY-PAIR → RELATIONSHIP TYPE MAPPING (Approach B: Generic Relationship Fix)
# ═══════════════════════════════════════════════════════════════════════════════
# When extraction produces generic types (belongs_to, contained_in, part_of)
# that get normalized to RELATED_TO or CHILD_OF, this mapping re-types them
# based on the source and target entity types.
#
# Root cause: Table-derived text from MinerU/VLM has entities co-occurring
# without prose connectors, so the LLM defaults to generic relationships.
# ═══════════════════════════════════════════════════════════════════════════════

# NOTE: _infer_entity_type and _infer_entity_types_parallel REMOVED
# With Pydantic validation in extraction, LLM-based entity type correction is no longer needed.
# Invalid types are caught and coerced during extraction, not post-hoc.
# This saves LLM API costs and processing time.
# NOTE: Algorithm functions moved to src/inference/algorithms/ modules
# Orchestrated by run_all_algorithms_parallel() from src.inference.algorithms



@dataclass
class SemanticPostProcessingRun:
    """Own one semantic post-processing run end-to-end."""

    rag_storage_path: str
    llm_model_name: str
    temperature: float = 0.1
    neo4j_io_factory: Callable[[], Neo4jGraphIO] = Neo4jGraphIO
    algorithm_runner: Callable[..., Awaitable[list[dict[str, Any]]]] = run_all_algorithms_parallel
    sync_discoveries_to_vdb_fn: Callable[..., Awaitable[dict[str, Any]]] | None = None
    start_time: float = field(default_factory=time.time, init=False)
    phase_times: dict[str, float] = field(default_factory=dict, init=False)
    starting_entity_count: int = field(default=0, init=False)
    starting_relationship_count: int = field(default=0, init=False)
    entities_corrected: int = field(default=0, init=False)
    relationships_retyped: int = field(default=0, init=False)
    relationships_inferred: int = field(default=0, init=False)
    relationships_synced: int = field(default=0, init=False)
    vdb_sync_stats: dict[str, Any] = field(default_factory=dict, init=False)
    neo4j_io: Neo4jGraphIO | None = field(default=None, init=False)

    async def run(self) -> Dict:
        logger.info("\n📊 Initializing Neo4j connection...")
        self.neo4j_io = self.neo4j_io_factory()

        try:
            entities, relationships = self._load_graph()
            if not entities:
                logger.warning("⚠️  No entities found in Neo4j workspace")
                return {
                    "status": "skipped",
                    "reason": "no_entities",
                    "entities_corrected": 0,
                    "relationships_inferred": 0,
                    "processing_time": 0,
                }

            await self._normalize_entities(entities)
            entities, relationships, grouped = self._normalize_relationships()
            await self._infer_relationships(entities, relationships, grouped)
            await self._sync_vdb()
            result = self._build_result()
            self._log_summary(result)
            return result
        except Exception as exc:
            logger.error("❌ Error during Neo4j post-processing: %s", exc, exc_info=True)
            return {
                "status": "error",
                "error": str(exc),
                "entities_corrected": 0,
                "relationships_inferred": 0,
                "processing_time": time.time() - self.start_time,
            }
        finally:
            if self.neo4j_io is not None:
                self.neo4j_io.close()

    def _io(self) -> Neo4jGraphIO:
        if self.neo4j_io is None:
            raise RuntimeError("Neo4j I/O not initialized")
        return self.neo4j_io

    def _complete_phase(self, phase_name: str, phase_start: float) -> None:
        self.phase_times[phase_name] = time.time() - phase_start
        logger.info(f"  ⏱️  {phase_name} completed in {self.phase_times[phase_name]:.1f}s")

    def _load_graph(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        phase_name = "Phase 1 · Data Loading"
        phase_start = time.time()
        logger.info("\n📥 Phase 1 · Data Loading: Reading knowledge graph from Neo4j...")
        entities = self._io().get_all_entities()
        relationships = self._io().get_all_relationships()
        self.starting_entity_count = len(entities)
        self.starting_relationship_count = len(relationships)
        logger.info(
            "  📊 Starting graph snapshot: %s entities, %s relationships",
            self.starting_entity_count,
            self.starting_relationship_count,
        )
        self._complete_phase(phase_name, phase_start)
        return entities, relationships

    async def _normalize_entities(self, entities: list[dict[str, Any]]) -> None:
        phase_name = "Phase 2 · Entity Normalization"
        phase_start = time.time()
        logger.info("\n🔧 Phase 2 · Entity Normalization: Lightweight type cleanup...")

        grouped = group_entities_by_type(entities)
        entity_updates, unknown_entities, table_mapped, hash_cleaned = plan_entity_type_updates(
            grouped,
            allowed_types=ALLOWED_TYPES,
            table_type_mapper=_heuristic_table_type_mapping,
        )

        if table_mapped > 0:
            logger.info("  📊 Processing %s generic table entities...", table_mapped)
            logger.info("  ✅ Heuristically mapped %s table entities", table_mapped)
        if hash_cleaned > 0:
            logger.info("  ✅ Cleaned %s prefixed entity types (#, #|, |)", hash_cleaned)

        unknown_retyped = await self._retype_unknown_entities(unknown_entities, entity_updates)
        if unknown_retyped > 0:
            logger.info(
                "  ✅ LLM retyped %s/%s UNKNOWN entities",
                unknown_retyped,
                len(unknown_entities),
            )

        if entity_updates:
            logger.info("\n💾 Updating %s entity types in Neo4j...", len(entity_updates))
            self.entities_corrected = self._io().update_entity_types(entity_updates)
        else:
            logger.info("\n✅ No entity type corrections needed (native LightRAG extraction working)")

        entities_after_update = self._io().get_all_entities()
        name_updates, canonical_mapping = plan_entity_name_updates(
            group_entities_by_type(entities_after_update)
        )
        if name_updates:
            logger.info("\n🪪 Canonicalizing %s entity names...", len(name_updates))
            self._io().update_entity_names(name_updates)
            vdb_name_stats = apply_entity_name_updates_to_vdb(
                self.rag_storage_path,
                canonical_mapping,
            )
            entities_after_update = self._io().get_all_entities()
            if vdb_name_stats["entities_updated"] > 0 or vdb_name_stats["relationships_updated"] > 0:
                logger.info(
                    "  ✅ Synced %s entity names and %s relationship endpoints to VDB JSON",
                    vdb_name_stats["entities_updated"],
                    vdb_name_stats["relationships_updated"],
                )

        # Always mirror Neo4j metadata into VDB JSON. LightRAG ingest does not
        # reliably populate entity_type on vdb_entities.json; skipping sync when
        # Phase 2 made no corrections left skills with empty typed slices.
        entities_synced = sync_entity_metadata_to_vdb(
            self.rag_storage_path,
            entities_after_update,
        )
        if entities_synced > 0:
            logger.info("  ✅ Synced %s entity metadata rows back to vdb_entities.json", entities_synced)
        else:
            logger.info("  ✅ VDB entity metadata already aligned with Neo4j")

        self._complete_phase(phase_name, phase_start)

    async def _retype_unknown_entities(
        self,
        unknown_entities: list[dict[str, Any]],
        entity_updates: list[dict[str, Any]],
    ) -> int:
        if not unknown_entities:
            return 0

        logger.info("  🔍 Retyping %s UNKNOWN entities with LLM...", len(unknown_entities))
        from src.inference.entity_operations import retype_entities_batch
        from src.utils.llm_client import call_llm_async

        async def llm_func(prompt: str, system_prompt: str) -> str:
            return await call_llm_async(
                prompt=prompt,
                model=self.llm_model_name,
                system_prompt=system_prompt,
                temperature=0.1,
            )

        unknown_retyped = 0
        batch_size = 20
        for index in range(0, len(unknown_entities), batch_size):
            batch = unknown_entities[index : index + batch_size]
            try:
                retyped = await retype_entities_batch(batch, llm_func)
                for entity in batch:
                    entity_name = entity.get("entity_name")
                    if entity_name not in retyped:
                        continue
                    new_type = retyped[entity_name]
                    if new_type and new_type.lower() != "unknown":
                        entity_updates.append(
                            {"id": entity["id"], "new_entity_type": new_type.lower()}
                        )
                        unknown_retyped += 1
                        logger.debug("    Retyped '%s': UNKNOWN → %s", entity_name, new_type)
            except Exception as exc:
                logger.warning(
                    "  ⚠️ Failed to retype batch %s: %s",
                    index // batch_size + 1,
                    exc,
                )

        return unknown_retyped

    def _normalize_relationships(
        self,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        phase_name = "Phase 3 · Rel Normalization"
        phase_start = time.time()
        logger.info(
            "\n🔗 Phase 3 · Relationship Normalization: Resolving generic types (entity-pair lookup)..."
        )

        entities = self._io().get_all_entities()
        relationships = self._io().get_all_relationships()
        entity_by_id = {entity["id"]: entity for entity in entities}
        retype_updates = collect_relationship_retype_updates(relationships, entity_by_id)

        if retype_updates:
            logger.info("  Found %s generic relationships to retype", len(retype_updates))
            self.relationships_retyped = self._io().retype_relationships(retype_updates)
        else:
            logger.info("  ✅ No generic relationships need retyping")

        grouped = group_entities_by_type(entities)
        self._complete_phase(phase_name, phase_start)
        return entities, relationships, grouped

    async def _infer_relationships(
        self,
        entities: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        grouped: dict[str, list[dict[str, Any]]],
    ) -> None:
        phase_name = "Phase 4 · Rel Inference"
        phase_start = time.time()
        logger.info("\n🔗 Phase 4 · Relationship Inference: Running parallel algorithms...")

        new_relationships = await self.algorithm_runner(
            entities=entities,
            entities_by_type=grouped,
            id_to_entity={entity["id"]: entity for entity in entities},
            neo4j_io=self._io(),
            model=self.llm_model_name,
            temperature=self.temperature,
            existing_relationships=relationships,
        )

        if new_relationships:
            logger.info("\n💾 Creating %s new relationships in Neo4j...", len(new_relationships))
            self.relationships_inferred = self._io().create_relationships(new_relationships)
        else:
            logger.info("\n✅ No new relationships inferred")

        self._complete_phase(phase_name, phase_start)

    async def _sync_vdb(self) -> None:
        phase_name = "Phase 5 · VDB Sync"
        phase_start = time.time()
        logger.info("\n🔄 Phase 5 · VDB Synchronization: Syncing inferred relationships...")

        sync_fn = self.sync_discoveries_to_vdb_fn
        if sync_fn is None:
            from src.inference.vdb_sync import sync_discoveries_to_vdb as sync_fn

        self.vdb_sync_stats = await sync_fn(
            neo4j_io=self._io(),
            relationships_inferred=self.relationships_inferred,
        )
        self.relationships_synced = self.vdb_sync_stats.get("relationships_synced", 0)

        if self.vdb_sync_stats.get("status") == "success":
            logger.info(
                "✅ VDB sync complete: %s relationships now queryable",
                self.relationships_synced,
            )
        elif self.vdb_sync_stats.get("status") == "skipped":
            logger.warning(
                "⚠️ VDB sync skipped: %s",
                self.vdb_sync_stats.get("reason", "unknown"),
            )
        else:
            logger.error(
                "❌ VDB sync failed: %s",
                self.vdb_sync_stats.get("error", "unknown"),
            )

        self._complete_phase(phase_name, phase_start)

    def _build_result(self) -> dict[str, Any]:
        processing_time = time.time() - self.start_time
        return build_post_processing_result(
            rag_storage_path=self.rag_storage_path,
            type_counts=self._io().get_entity_count_by_type(),
            rel_counts=self._io().get_relationship_count_by_type(),
            entities_corrected=self.entities_corrected,
            relationships_inferred=self.relationships_inferred,
            relationships_synced=self.relationships_synced,
            processing_time=processing_time,
            starting_entity_count=self.starting_entity_count,
            starting_relationship_count=self.starting_relationship_count,
            vdb_sync_status=self.vdb_sync_stats.get("status", "unknown"),
        )

    def _log_summary(self, result: dict[str, Any]) -> None:
        processing_time = result["processing_time"]
        type_counts = result["entity_type_counts"]
        rel_counts = result["relationship_type_counts"]

        logger.info("\n" + "=" * 80)
        logger.info("✅ SEMANTIC POST-PROCESSING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"  Total time:              {processing_time:.1f}s")
        for phase_name, phase_duration in self.phase_times.items():
            logger.info(f"    {phase_name:30s}  {phase_duration:6.1f}s")
        logger.info(f"  Entities corrected:      {self.entities_corrected}")
        logger.info(f"  Relationships retyped:   {self.relationships_retyped}")
        logger.info(f"  Relationships inferred:  {self.relationships_inferred}")
        logger.info(f"  Relationships synced:    {self.relationships_synced}")
        logger.info(f"  Processing time:         {processing_time:.2f}s")
        logger.info("=" * 80)

        logger.info("\n📊 Entity Type Distribution (ALL 18 types):")
        for entity_type, count in sorted(type_counts.items(), key=lambda item: item[1], reverse=True):
            logger.info(f"  {entity_type:30s}: {count:4d}")

        logger.info("\n📊 Relationship Type Distribution (final Neo4j graph):")
        for relationship_type, count in sorted(rel_counts.items(), key=lambda item: item[1], reverse=True):
            logger.info(f"  {relationship_type:30s}: {count:4d}")

        logger.info("\n" + "=" * 60)
        logger.info("📈 FINAL COUNTS (after all processing complete):")
        logger.info("=" * 60)
        logger.info(f"  Final Neo4j Entities:          {result['final_entity_count']}")
        logger.info(f"  Final Neo4j Relationships:     {result['final_relationship_count']}")
        if result["vdb_entity_count"] is not None:
            logger.info(f"  Final VDB Entity Entries:      {result['vdb_entity_count']}")
        if result["vdb_relationship_count"] is not None:
            logger.info(f"  Final VDB Relationship Entries: {result['vdb_relationship_count']}")
        logger.info(f"  ─────────────────────────────────────")
        logger.info(f"  Post-Processing Retyped Rels:  {self.relationships_retyped}")
        logger.info(f"  Post-Processing Added Rels:    {self.relationships_inferred}")
        logger.info(f"  VDB Synced Relationships:      {self.relationships_synced}")
        logger.info("=" * 60)


async def _semantic_post_processor_neo4j(
    llm_model_name: str = None,
    temperature: float = 0.1,
    rag_storage_path: str = "./rag_storage",
) -> Dict:
    """Run semantic post-processing against Neo4j-backed workspace graph."""
    settings = get_settings()
    if llm_model_name is None:
        llm_model_name = settings.post_processing_llm_name

    return await SemanticPostProcessingRun(
        rag_storage_path=rag_storage_path,
        llm_model_name=llm_model_name,
        temperature=temperature,
    ).run()


async def enhance_knowledge_graph(
    rag_storage_path: str,
    llm_func: Callable[[str, str], Awaitable[str]],
    batch_size: int = 50
) -> Dict:
    """
    Run semantic post-processing on extracted knowledge graph (Neo4j).
    
    5-phase semantic post-processor:
    1. Data Loading - read entities/relationships from Neo4j
    2. Entity Normalization - fix table/hash types
    3. Relationship Normalization - retype generic RELATED_TO
    4. Relationship Inference - L↔M links, doc structure, orphan resolution
    5. VDB Synchronization - sync inferred rels to vector DB
    
    Args:
        rag_storage_path: Path to rag_storage directory (unused - kept for API compatibility)
        llm_func: Async LLM function (unused - we use centralized call_llm_async)
        batch_size: Batch size for LLM calls (default: 50)
    
    Returns:
        Stats dict with:
        - relationships_inferred: Number of new relationships
        - processing_time: Total time in seconds
    """
    # Get LLM model from centralized settings - use REASONING model for post-processing
    settings = get_settings()
    llm_model = settings.post_processing_llm_name
    llm_temp = settings.llm_model_temperature
    
    # Startup banner with active configuration
    logger.info("")
    logger.info("=" * 80)
    logger.info("🧠 SEMANTIC POST-PROCESSING: 5-Phase Pass")
    logger.info("=" * 80)
    logger.info(f"  Post-Processing Model: {llm_model}")
    logger.info(f"  Temperature:           {llm_temp}")
    logger.info(f"  Workspace Path:        {rag_storage_path}")
    logger.info("  Phases: Data Loading → Entity Norm → Rel Norm → Inference → VDB Sync")
    logger.info("=" * 80)
    
    return await _semantic_post_processor_neo4j(
        llm_model_name=llm_model,
        temperature=llm_temp,
        rag_storage_path=rag_storage_path,
    )
