"""Multimodal prompt and processor setup for RAG-Anything."""

from __future__ import annotations

import logging

from prompts.multimodal.govcon_multimodal_prompts import GOVCON_MULTIMODAL_PROMPTS
from raganything.modalprocessors import (
    EquationModalProcessor,
    ImageModalProcessor,
    TableModalProcessor,
)
from raganything.prompt_manager import register_prompt_language, set_prompt_language

logger = logging.getLogger(__name__)


def register_govcon_multimodal_prompts() -> None:
    """Register and activate govcon prompt language for multimodal analysis."""
    register_prompt_language("govcon", GOVCON_MULTIMODAL_PROMPTS)
    set_prompt_language("govcon")
    logger.info(
        "✅ Registered and activated 'govcon' prompt language (%d prompt overrides)",
        len(GOVCON_MULTIMODAL_PROMPTS),
    )
    logger.info("   - TABLE_ANALYSIS_SYSTEM: federal acquisition analyst + workload/CLIN/CDRL focus")
    logger.info("   - table_prompt(_with_context): multi-page continuation detection, govcon directives")
    logger.info("   - IMAGE_ANALYSIS_SYSTEM: org charts, facility layouts, CDRL hierarchies")
    logger.info("   - vision_prompt(_with_context): all visible text + contractual element extraction")
    logger.info("   - EQUATION prompts: performance formulas, incentive calculations")
    logger.info("   - QUERY_TABLE/IMAGE prompts: govcon analyst framing for query-time VLM")


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