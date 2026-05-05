"""Shared GovCon prompt registration helpers for server startup."""

from __future__ import annotations

from typing import Any, Callable, Mapping, MutableMapping

GOVCON_PROMPT_LANGUAGE = "govcon"


def apply_lightrag_govcon_prompts(
    *,
    prompt_map: MutableMapping[str, Any],
    govcon_prompts: Mapping[str, Any],
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
    multimodal_prompts: Mapping[str, Any],
    register_prompt_language_func: Callable[[str, Mapping[str, Any]], None],
    set_prompt_language_func: Callable[[str], None],
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