"""
GovCon Prompts for LightRAG
===========================
Federal Government Contracting Knowledge Graph Extraction Prompts

This module extends LightRAG's battle-tested prompt.py framework with
domain-specific government contracting intelligence for RFP analysis.

Architecture:
-------------
- V8 compact frame composed in-module by _build_v8_system_prompt()
- Entity-type guidance rendered dynamically from the YAML entity catalog
- Relationship guidance rendered dynamically from src/ontology/schema.py
- Part G examples externalized via LightRAG ENTITY_TYPE_PROMPT_FILE profile
- LightRAG-compatible format with JSON structured output

Philosophy:
-----------
1. LEVERAGE LightRAG's proven extraction architecture (entity/relation format, delimiters)
2. INJECT complete GovCon domain expertise (not a summary - the FULL intelligence)
3. PRESERVE LightRAG's prompt keys for seamless integration via PROMPTS.update()

Usage:
------
    from prompts.govcon_prompt import GOVCON_PROMPTS
    from lightrag.prompt import PROMPTS
    PROMPTS.update(GOVCON_PROMPTS)

Domain Intelligence Included (V8 compact frame — 8 sections):
-------------------------------------------------------------
- Part A: Role Definition (8 Shipley user personas)
- Part B: Core Extraction Rules (content/density/naming/split/hierarchy/hygiene)
- Part C: Quantitative Preservation (verbatim numbers, rates, IDs, dates)
- Part D: Entity Catalog ({entity_types_guidance} — rendered from YAML at init)
- Part E: Relationship Guidance (rendered from schema.py canonical 26-type set)
- Part F: Output Contract (JSON shape, field rules)
- Part G: Annotated RFP Examples ({examples} — from prompts/entity_type/govcon.yaml)
- Part H: Quality Checks Before Output

Version: 8.4.0 (V8-4 legacy monolith retired, V8 is sole extraction system prompt, issue #124)

Prompt Changelog:
-----------------
v8.4.0 - V8-4: Delete govcon_lightrag_json.txt legacy monolith. Remove USE_V8_PROMPT
         feature flag. _build_v8_system_prompt() is now the sole extraction system prompt.
         Validated across ADAB (non-UCF, 7/11 win) and MCPP (UCF, parity) before retirement.
v8.1.0 - Add USE_V8_PROMPT compact-frame path. Compact frame composes relationship
         guidance from schema.py and keeps entity guidance/examples as dynamic injections.
         Legacy monolith retained as fallback for A/B validation (now retired in v8.4.0).
v8.0.0 - Replace static Part K example block with `{examples}` placeholder.
         All 7 JSON examples now live in prompts/entity_type/govcon.yaml and are
         loaded via LightRAG ENTITY_TYPE_PROMPT_FILE. Example drift repaired to
         match the reduced canonical relationship vocabulary.
v7.3.1 - Anonymize Examples 2, 3, 4 with generic [...] placeholders.
         Removes AFCAP-specific proper nouns so model learns extraction shape,
         not domain-brittle vocabulary. Each example has a Note: listing RFP
         contexts it applies to. Strip entire dev metadata header block from
         prompt (~340 tokens saved — zero extraction value).
v7.3.0 - Remove Examples 3 (FAR/DFARS clause list) and 6 (special events/training)
         from Part K. Both redundant with Part C/F/G rules. 9 → 7 examples.
v7.2.1 - Anonymize Example 9 (was ADAB-specific TOMP/MEP/CTIP/QCP specimen).
v7.2   - Close Q1/Q5/Q6 recall regressions vs TUPLE baseline. Add Part F.0
         L↔M completeness mandate, Part J density floor, Example 9 high-density.
v7.1   - Forbid space/comma-joined canonical types in keywords field.
         Net Phase 3 token savings: ~1,670 tokens (5.7%), 29,322 → 27,652.

Changelog:
----------
v3.4.0 (Apr 2026) - JSON Structured-Output Extraction (issue #124, Phase 1.2)
  - Added entity_extraction_json_system_prompt loaded from govcon_lightrag_json.txt
    (materialized by tools/_build_json_prompt.py from the canonical native.txt).
  - Added entity_extraction_json_user_prompt and entity_continue_extraction_json_user_prompt
    matching the LightRAG 1.5.0 JSON-mode contract (output is a single JSON object with
    `entities` and `relationships` arrays; no tuple/completion delimiters).
  - Added entity_extraction_json_examples=[<one-line Part K back-reference>]
    (upstream requires non-empty list; real examples are inlined in Part K)
    (the 8 govcon examples are embedded inline in Part K of the system prompt).
  - Tuple-mode keys (entity_extraction_system_prompt, entity_extraction_user_prompt,
    entity_continue_extraction_user_prompt, entity_extraction_examples) retained for
    rollback during Phase 1.2/1.3 validation. TODO(phase-2.5): delete after JSON lockin.
  - Canonical relationship type encoding: emitted as the first comma-separated token of
    each relationship's `keywords` field — matches LightRAG's storage contract for both
    tuple and JSON paths, so vdb_sync.normalize_relationship_type() needs no change.

v3.3.0 (Apr 2026) - Format-Agnostic Mentor Persona (UCF + non-UCF)
  - Added "Solicitation Format Awareness" block to rag_response and naive_rag_response.
    Mentor now treats UCF (Section A-M) and non-UCF (FAR 16 task orders, FOPRs, BPA calls,
    OTAs, agency-specific) as equally valid; reasons over entity types
    (proposal_instruction, evaluation_factor, requirement, deliverable, clause)
    instead of UCF section labels.
  - Replaced literal "Section L instructions" / "Section M evaluation criteria" phrasing
    in In Scope, Shipley Framework, Pattern Recognition, and Communication Style blocks
    with entity-type vocabulary plus parenthetical UCF mappings for Shipley reader
    recognition.
  - Mentor must NOT tell the user a requirement is missing because it lacks a literal
    "Section L" or "Section M" heading — must map by entity, not label.

v3.2.0 (Apr 2026) - Inline Citation Markers
  - rag_response and naive_rag_response now require `[N]` markers placed inline
    next to each claim sourced from a numbered reference. Enables UI citation
    chips (branch 102) to wrap and link those markers to the References list.
  - Markers must use the SAME number as the corresponding entry in `### References`.
  - Multiple sources for one claim are written as `[1, 3]`. No new instructions
    about reference-list shape; only adds the inline placement requirement.

v3.1.1 (Apr 2026) - Scope contract correction: Phase 3-6 → Phase 4-6
  - Theseus is a Shipley Phase 4-6 system (Proposal Planning → Proposal Development → Post-Submittal Activities).
    Phase 3 (Capture/Opportunity Planning) is pre-RFP and ends at the Bid Validation Decision gate;
    Theseus engages AFTER that gate, when the Final RFP has been received.
  - Out-of-scope band widened to Phase 0-3 (all pre-RFP capture work, including Capture/Opportunity
    Planning itself).

v3.1.0 (Apr 2026) - Theseus Scope Contract (initial; phase numbers later corrected in v3.1.1)
  - Added "Theseus Scope" section to rag_response and naive_rag_response
  - Declares Theseus is a proposal-development system (activated when RFP drops)
  - Defines in-scope topics: Section L/M decoding, compliance matrix, win themes, FAB,
    color teams, BOE discipline, FAR/DFARS compliance, lessons learned, Explicit Benefit Linkage Rule
  - Defines out-of-scope pre-RFP capture topics: Bid/No-Bid, Pwin recalibration, opportunity
    shaping, customer call planning, teaming renegotiation, PTW, competitive intelligence, gate reviews
  - Mentor treats capture-phase retrieval as upstream input, not a topic to re-open
  - Role phrasing shifted from "capture strategist and proposal consultant" to
    "proposal strategist and mentor" to reinforce drafting-phase focus
  - Preserves Win/Loss learning and FAR 15.506 debrief awareness as in-scope (they shape
    what evaluators look for NOW)

v3.0.0 (Apr 2026) - Shipley Mentor Framework + Model Upgrade
  - Complete rewrite of rag_response and naive_rag_response Role/Goal/Instructions
  - Role: Senior consultant/mentor who teaches capture methodology, not just answers questions
  - Added Shipley Consulting Framework section grounding key terms (discriminator, FAB, ghost, hot button)
  - Model upgraded from grok-4-1-fast-reasoning to grok-4.20-0309-reasoning (lowest hallucination rate, strict prompt adherence)
  - Proactive pattern recognition: surface risks, contradictions, and opportunities unprompted
  - Strategic implication requirement: every fact must be accompanied by "what this means for your bid"
  - Escalation signaling with warning markers for compliance risks and RFP ambiguities
  - Audience shifted from "briefing a capture manager" to "mentoring someone building capture expertise"

v2.4.0 (Jan 2026) - Exploratory Query & Reference Enhancements
  - Added KG consultation guidance for exploratory/brainstorming queries
  - Prioritizes Shipley methodology entities (win themes, discriminators, hot buttons)
  - Added page/section reference notation guidance when available in context
  - Updated reference examples to show section/page format

v2.3.0 (Jan 2026) - Issue #69 Enhancement: Communication Style Guidance
  - Added "Communication Style" section to rag_response and naive_rag_response
  - Expand acronyms on first use (FFP, FAR, DFAR, etc.)
  - Explain reasoning behind claims, not just state conclusions
  - Write for intelligent non-experts; avoid unexplained jargon
  - Explain WHY retrieved context matters, not just THAT it exists

v2.2.0 (Jan 2026) - Issue #69: Strategic Analysis Mode for Reasoning LLM
  - Transformed rag_response and naive_rag_response from robotic fact-dump to senior consultant
  - Role: "Senior GovCon capture strategist" not "AI assistant"
  - Enables reasoning, interpretation, and strategic recommendations
  - Maintains grounding: all factual claims must trace to retrieved context
  - Explicitly permits: drawing implications, applying domain expertise, proactive insights
  - Eliminates defensive "I don't have enough information" when reasoning can help

v2.1.0 (Dec 2025) - Issue #60: RAG Response Accessibility
  - Added "Accessibility & Explanation Quality" instruction to rag_response and naive_rag_response
  - Acronyms must be spelled out on first use
  - Assume non-expert audience; explain GovCon concepts briefly
  - Use bulleted lists instead of tables (better chat rendering)
  - Recommendations must include WHY with evidence
  - Prefer thoroughness over brevity
"""

from __future__ import annotations

from typing import Any

from dotenv import load_dotenv

from prompts.govcon import EXTRACTION_PROMPTS, QUERY_PROMPTS, build_v8_system_prompt

# CRITICAL: load .env before prompt assembly — this module may be imported
# before the server entry-point's load_dotenv() has run (e.g. during tests or
# when govcon_prompt.py is evaluated by native LightRAG startup).
load_dotenv(override=True)


GOVCON_PROMPTS: dict[str, Any] = {}

# ═══════════════════════════════════════════════════════════════════════════════
# Extraction prompt packaging seam:
# - govcon_prompt.py remains the compatibility facade imported by runtime/tests/tools
# - prompts.govcon.extraction owns extraction-specific prompt assembly and keys


def _build_v8_system_prompt() -> str:
    """Compatibility facade for tests and docs that import from govcon_prompt.py."""
    return build_v8_system_prompt()


GOVCON_PROMPTS.update(EXTRACTION_PROMPTS)
GOVCON_PROMPTS.update(QUERY_PROMPTS)


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE INITIALIZATION AND VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_prompts():
    """Validate that full domain intelligence was loaded"""
    extraction_prompt = GOVCON_PROMPTS.get("entity_extraction_json_system_prompt", "")

    # V8 compact frame: ~5K–8K chars (well under the legacy ~121K-char monolith).
    MIN_EXPECTED_CHARS = 5000

    if len(extraction_prompt) < MIN_EXPECTED_CHARS:
        import warnings
        warnings.warn(
            f"GovCon extraction prompt appears truncated ({len(extraction_prompt):,} chars). "
            f"Expected at least {MIN_EXPECTED_CHARS:,} chars."
        )

    # Validate that all V8 structural sections are present.
    # Part D is a {entity_types_guidance} placeholder — rendered from YAML at LightRAG init.
    # Part G is an {examples} placeholder — resolved from prompts/entity_type/govcon.yaml.
    required_sections = [
        "PART A: ROLE DEFINITION (V8 COMPACT FRAME)",
        "PART B: CORE EXTRACTION RULES",
        "{entity_types_guidance}",
        "PART E: RELATIONSHIP GUIDANCE",
        "PART G: ANNOTATED RFP EXAMPLES",
    ]

    missing = [s for s in required_sections if s not in extraction_prompt]
    if missing:
        import warnings
        warnings.warn(f"GovCon extraction prompt missing sections: {missing}")


# Run validation on import
_validate_prompts()


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = ["GOVCON_PROMPTS"]
