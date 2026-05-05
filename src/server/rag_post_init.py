"""Post-initialization wiring for an already-initialized RAGAnything instance."""

from __future__ import annotations

import logging
import os

from lightrag.prompt import PROMPTS
from prompts.multimodal.govcon_multimodal_prompts import GOVCON_MULTIMODAL_PROMPTS
from raganything.modalprocessors import (
    EquationModalProcessor,
    ImageModalProcessor,
    TableModalProcessor,
)
from raganything.prompt_manager import register_prompt_language, set_prompt_language

from prompts.govcon_prompt import GOVCON_PROMPTS
from src.server.doc_status_compat import apply_doc_status_compatibility_shim
from src.server.processing_callback import get_processing_callback

logger = logging.getLogger(__name__)

GOVCON_PROMPT_LANGUAGE = "govcon"


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


def apply_lightrag_govcon_prompts(
    *,
    prompt_map,
    govcon_prompts,
    log,
) -> None:
    """Replace LightRAG prompts with the GovCon prompt set."""
    prompt_map.update(govcon_prompts)
    extraction_prompt = str(govcon_prompts.get("entity_extraction_json_system_prompt", ""))
    extraction_chars = len(extraction_prompt)
    extraction_lines = extraction_prompt.count("\n")
    log.info("✅ REPLACED LightRAG prompt system with GovCon prompt overrides")
    log.info(
        "   Extraction prompt: %s chars (~%s tokens), %s lines",
        f"{extraction_chars:,}",
        f"{extraction_chars // 4:,}",
        f"{extraction_lines:,}",
    )
    log.info("   Source: V8 compact frame (govcon_prompt.py builder)")
    log.info("   Domain Intelligence:")
    log.info("     • Entity catalog rendered dynamically from govcon_entity_types.yaml")
    log.info("     • Relationship guidance rendered from schema.py 26-type canonical set")
    log.info("     • 7 annotated RFP examples injected from prompts/entity_type/govcon.yaml")
    log.info("     • Quantitative preservation rules for BOE development")
    log.info("     • Compact frame + quality checks (Parts A-H)")
    log.info(
        "   Keywords examples: %d GovCon-specific",
        len(govcon_prompts.get("keywords_extraction_examples", [])),
    )


def activate_govcon_multimodal_prompts(
    *,
    multimodal_prompts,
    register_prompt_language_func,
    set_prompt_language_func,
    log,
) -> None:
    """Register and activate the GovCon prompt language for multimodal analysis."""
    register_prompt_language_func(GOVCON_PROMPT_LANGUAGE, multimodal_prompts)
    set_prompt_language_func(GOVCON_PROMPT_LANGUAGE)
    log.info(
        "✅ Registered and activated '%s' prompt language (%d prompt overrides)",
        GOVCON_PROMPT_LANGUAGE,
        len(multimodal_prompts),
    )
    log.info("   - TABLE_ANALYSIS_SYSTEM: federal acquisition analyst + workload/CLIN/CDRL focus")
    log.info("   - table_prompt(_with_context): multi-page continuation detection, govcon directives")
    log.info("   - IMAGE_ANALYSIS_SYSTEM: org charts, facility layouts, CDRL hierarchies")
    log.info("   - vision_prompt(_with_context): all visible text + contractual element extraction")
    log.info("   - EQUATION prompts: performance formulas, incentive calculations")
    log.info("   - QUERY_TABLE/IMAGE prompts: govcon analyst framing for query-time VLM")


def register_govcon_multimodal_prompts() -> None:
    """Register and activate govcon prompt language for multimodal analysis."""
    activate_govcon_multimodal_prompts(
        multimodal_prompts=GOVCON_MULTIMODAL_PROMPTS,
        register_prompt_language_func=register_prompt_language,
        set_prompt_language_func=set_prompt_language,
        log=logger,
    )


def register_native_modal_processors(rag_anything, *, llm_model_func, vision_model_func) -> None:
    """Register native modal processors against the active govcon prompt language."""
    context_extractor = rag_anything.context_extractor
    if context_extractor:
        logger.info(
            "✅ Context extractor available: window=%s, mode=%s",
            context_extractor.config.context_window,
            context_extractor.config.context_mode,
        )
    else:
        logger.warning("⚠️ Context extractor not available - tables will be processed without section context")

    rag_anything.modal_processors["table"] = TableModalProcessor(
        rag_anything.lightrag,
        llm_model_func,
        context_extractor,
    )
    rag_anything.modal_processors["image"] = ImageModalProcessor(
        rag_anything.lightrag,
        vision_model_func,
        context_extractor,
    )
    rag_anything.modal_processors["equation"] = EquationModalProcessor(
        rag_anything.lightrag,
        llm_model_func,
        context_extractor,
    )

    logger.info("✅ Native RAGAnything modal processors registered with govcon prompts")
    logger.info("   table    → TableModalProcessor    (govcon TABLE_ANALYSIS_SYSTEM + table_prompt)")
    logger.info("   image    → ImageModalProcessor    (govcon IMAGE_ANALYSIS_SYSTEM + vision_prompt)")
    logger.info("   equation → EquationModalProcessor (govcon EQUATION_ANALYSIS_SYSTEM + equation_prompt)")


def apply_role_llm_funcs_shim(rag_anything) -> None:
    """Patch LightRAG config views so RAG-Anything multimodal code can see role_llm_funcs."""
    lightrag = rag_anything.lightrag
    build_global_config = getattr(lightrag, "_build_global_config", None)
    live_role_funcs = getattr(lightrag, "role_llm_funcs", None)
    if not callable(build_global_config) or not live_role_funcs:
        logger.warning(
            "⚠️ Cannot apply role_llm_funcs shim: _build_global_config callable=%s, role_llm_funcs available=%s — modal multimodal extraction may fall back to bare table/image/equation placeholders",
            callable(build_global_config),
            bool(live_role_funcs),
        )
        return

    try:
        full_global_config = build_global_config()
        lightrag.__dict__["role_llm_funcs"] = full_global_config.get("role_llm_funcs", {})

        patched = 0
        for modal_kind, modal_processor in rag_anything.modal_processors.items():
            try:
                modal_processor.global_config = full_global_config
                patched += 1
            except Exception as shim_err:  # pragma: no cover - defensive
                logger.warning(
                    "⚠️ role_llm_funcs shim failed for modal processor '%s': %s",
                    modal_kind,
                    shim_err,
                )

        logger.info(
            "✅ Shim applied: injected role_llm_funcs into lightrag.__dict__ (roles=%s) AND rebuilt global_config for %d modal processors (workaround for raganything 1.2.10 ↔ lightrag 1.5.0 property/asdict bug)",
            sorted(live_role_funcs.keys()),
            patched,
        )
    except Exception as shim_err:
        logger.error(
            "❌ role_llm_funcs shim failed: %s — multimodal extraction will fall back to bare table/image/equation placeholders",
            shim_err,
        )


def configure_multimodal_stack(rag_anything, *, llm_model_func, vision_model_func) -> None:
    """Apply govcon multimodal prompt, processor, and shim setup."""
    register_govcon_multimodal_prompts()
    register_native_modal_processors(
        rag_anything,
        llm_model_func=llm_model_func,
        vision_model_func=vision_model_func,
    )
    apply_role_llm_funcs_shim(rag_anything)


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