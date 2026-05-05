"""Post-initialization wiring for an already-initialized RAGAnything instance."""

from __future__ import annotations

import logging
import os

from lightrag.prompt import PROMPTS

from prompts.govcon_prompt import GOVCON_PROMPTS
from src.server.doc_status_compat import apply_doc_status_compatibility_shim
from src.server.multimodal_setup import configure_multimodal_stack
from src.server.processing_callback import get_processing_callback
from src.server.prompt_registration import apply_lightrag_govcon_prompts

logger = logging.getLogger(__name__)


def log_effective_extract_role(rag_anything, *, use_strict_schema: bool) -> None:
    """Log the effective extract-role response format after LightRAG init."""
    effective_extract_kwargs = dict(getattr(rag_anything.lightrag, "role_llm_kwargs", {}).get("extract") or {})
    effective_response_format = effective_extract_kwargs.get("response_format") or {}
    effective_schema = effective_response_format.get("json_schema") or {}
    extract_role_state = getattr(rag_anything.lightrag, "_role_llm_states", {}).get("extract")
    extract_metadata = getattr(extract_role_state, "metadata", {}) if extract_role_state else {}
    logger.info("=" * 88)
    logger.info("🔎 EFFECTIVE EXTRACT ROLE AFTER LightRAG INIT")
    logger.info("   response_format.type=%s", effective_response_format.get("type", "<none>"))
    logger.info("   json_schema.name=%s", effective_schema.get("name", "<none>"))
    logger.info("   strict=%s", effective_schema.get("strict", "<none>"))
    logger.info("   extract_cache_identity_host=%s", extract_metadata.get("host", "<unknown>"))
    if use_strict_schema and effective_response_format.get("type") != "json_schema":
        logger.error("❌ STRICT SCHEMA EXPECTED BUT NOT EFFECTIVE — do not process documents until fixed")
    logger.info("=" * 88)


def verify_govcon_chunker(rag_anything) -> None:
    """Log whether the GovCon chunker landed on the LightRAG instance."""
    active_chunker = getattr(rag_anything.lightrag, "chunking_func", None)
    chunker_name = getattr(active_chunker, "__name__", repr(active_chunker))
    if chunker_name == "govcon_chunking_func":
        logger.info("✅ GovCon chunking_func registered on LightRAG instance (banner injection active)")
        logger.info("   Every classified document chunk will start with [GOVCON_DOC: type=...; note=...]")
        logger.info("   Persisted chunks also carry govcon_doc_type metadata when classified")
        return
    logger.warning(
        "⚠️  Active chunking_func is '%s' (expected 'govcon_chunking_func'). Doc-type banners will NOT be injected.",
        chunker_name,
    )


def register_processing_callback(rag_anything, *, llm_model_func) -> None:
    """Register the shared GovCon processing callback on the RAGAnything instance."""
    processing_callback = get_processing_callback()
    processing_callback.set_llm_func(llm_model_func)
    rag_anything.callback_manager.register(processing_callback)
    logger.info("✅ GovConProcessingCallback registered with RAG-Anything callback_manager")


def extend_vdb_meta_fields(lightrag_instance) -> None:
    """Preserve Theseus metadata fields during LightRAG VDB upserts."""
    entity_meta = lightrag_instance.entities_vdb.meta_fields | {"entity_type", "description"}
    lightrag_instance.entities_vdb.meta_fields = entity_meta
    logger.info("✅ Extended entities_vdb.meta_fields: %s", entity_meta)

    relationship_meta = lightrag_instance.relationships_vdb.meta_fields | {"keywords", "description"}
    lightrag_instance.relationships_vdb.meta_fields = relationship_meta
    logger.info("✅ Extended relationships_vdb.meta_fields: %s", relationship_meta)


def apply_govcon_prompt_overrides() -> None:
    """Replace LightRAG prompts with the GovCon prompt set."""
    apply_lightrag_govcon_prompts(
        prompt_map=PROMPTS,
        govcon_prompts=GOVCON_PROMPTS,
        log=logger,
    )


async def maybe_bootstrap_ontology(rag_anything, *, settings, working_dir: str) -> None:
    """Optionally bootstrap curated GovCon domain knowledge into the workspace."""
    if not settings.auto_bootstrap_ontology:
        logger.info("📚 Ontology auto-bootstrap DISABLED (AUTO_BOOTSTRAP_ONTOLOGY=False)")
        return

    try:
        from src.ontology.bootstrap import bootstrap_govcon_ontology

        workspace_path = os.path.join(working_dir, settings.workspace)
        bootstrap_result = await bootstrap_govcon_ontology(
            lightrag=rag_anything.lightrag,
            working_dir=workspace_path,
            force=settings.ontology_bootstrap_force,
        )

        if bootstrap_result["status"] == "success":
            logger.info(
                "✅ GovCon ontology bootstrapped into workspace '%s': %s entities, %s relationships",
                settings.workspace,
                bootstrap_result["entities_added"],
                bootstrap_result["relationships_added"],
            )
        elif bootstrap_result["status"] == "already_bootstrapped":
            logger.info(
                "📚 GovCon ontology already bootstrapped into workspace '%s' (%s)",
                settings.workspace,
                bootstrap_result["bootstrapped_at"],
            )
        else:
            logger.warning("⚠️ Ontology bootstrap: %s", bootstrap_result.get("error", "unknown issue"))
    except Exception as exc:
        logger.warning("⚠️ Ontology bootstrap failed: %s - continuing without domain knowledge", exc)


async def finalize_rag_initialization(
    rag_anything,
    *,
    settings,
    working_dir: str,
    modal_llm_func,
    vision_model_func,
    use_strict_schema: bool,
) -> None:
    """Apply all post-init wiring after LightRAG internal init succeeds."""
    log_effective_extract_role(rag_anything, use_strict_schema=use_strict_schema)
    verify_govcon_chunker(rag_anything)
    register_processing_callback(rag_anything, llm_model_func=modal_llm_func)
    extend_vdb_meta_fields(rag_anything.lightrag)
    configure_multimodal_stack(
        rag_anything,
        llm_model_func=modal_llm_func,
        vision_model_func=vision_model_func,
    )
    apply_govcon_prompt_overrides()
    apply_doc_status_compatibility_shim(rag_anything.lightrag)
    await maybe_bootstrap_ontology(
        rag_anything,
        settings=settings,
        working_dir=working_dir,
    )