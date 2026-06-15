"""Shipped RFP Intelligence briefing prompts — single source for repeatable workflows.

All packaged Intel slice and related-skill prompts live here and merge into the
workspace Prompt Library (`channel` metadata binds entries to UI surfaces).
"""

from __future__ import annotations

from typing import Any

# channel values:
#   chat            — Capture Chat starters (default when omitted)
#   briefing_chat   — RFP Intelligence chat slice
#   briefing_skill  — RFP Intelligence primary skill slice
#   briefing_related — RFP Intelligence related skill on a parent slice

BRIEFING_PROMPT_LIBRARY: list[dict[str, Any]] = [
    {
        "phase": "4",
        "category": "RFP Briefing · Chat",
        "title": "Contract overview",
        "prompt": (
            "Provide an overview of the scope and services for this contract. "
            "Use an educational tone in plain language; expand acronyms on first use. "
            "Stay grounded in retrieved document terminology and facts — cite with [N]. "
            "Explain structure: contract type, periods, task/service areas, major deliverables, "
            "and key performance mechanisms."
        ),
        "channel": "briefing_chat",
        "slice_id": "overview",
        "sort_order": 10,
        "icon": "layout-dashboard",
        "label": "Contract overview",
        "description": (
            "Scope primer — contract type, periods, task areas, deliverables, "
            "and performance mechanisms."
        ),
    },
    {
        "phase": "4",
        "category": "RFP Briefing · Chat",
        "title": "Sites & locations",
        "prompt": (
            "Summarize all sites and locations in scope. Organize by country, then region. "
            "Note counts where the documents support them. Identify geographic clusters, "
            "OCONUS vs CONUS concentration, and any site-specific appendix patterns. "
            "Flag data gaps. Cite every factual claim with [N]."
        ),
        "channel": "briefing_chat",
        "slice_id": "sites",
        "sort_order": 20,
        "icon": "map-pin",
        "label": "Sites & locations",
        "description": (
            "Geographic inventory — CONUS/OCONUS clusters, site counts, "
            "and appendix patterns."
        ),
    },
    {
        "phase": "4",
        "category": "RFP Briefing · Chat",
        "title": "Evaluation decoder",
        "prompt": (
            "Decode all evaluation_factor and subfactor entities (UCF Section M or equivalent). "
            "For each: what the government is evaluating; stated weights or rating definitions "
            "if present; evidence or proof they expect; what a strong vs weak response looks "
            "like per document language. Ground every row in [N] citations."
        ),
        "channel": "briefing_chat",
        "slice_id": "evaluation",
        "sort_order": 30,
        "icon": "scale",
        "label": "Evaluation decoder",
        "description": (
            "Decode evaluation_factor entities — weights, proof expected, "
            "strong vs weak responses."
        ),
    },
    {
        "phase": "4",
        "category": "RFP Briefing · Skill",
        "title": "Mission Readiness Frame",
        "prompt": (
            "Build the Mission Readiness Frame from the full solicitation package "
            "(PWS/SOW, background, QASP, deliverables, evaluation criteria, amendments). "
            "Program office = customer; contract = workload enabler for readiness. "
            "Comprehensively surface pain points and theme opportunities — including non-obvious "
            "latent/structural challenges — each with cited rationale. Review current methods/tools "
            "implied by the PWS and identify customer-grounded innovation opportunities (quality up, "
            "cost down, or both; value without bloat; methods not only technology). "
            "Coverage is solicitation-driven — one eval crosswalk row per material factor/subfactor "
            "with plain-English reasoning; expand acronyms on first use as Full Term (ACR). "
            "Log missing factors in claim_gaps[] — never emit scaffold crosswalk rows."
        ),
        "channel": "briefing_skill",
        "slice_id": "mission-readiness",
        "skill": "mission-readiness-framer",
        "chain_preset": "mission-readiness",
        "sort_order": 40,
        "icon": "target",
        "label": "Mission Readiness Frame",
        "description": (
            "One click runs the full mission-readiness pipeline (six evidence slices + compile) "
            "and saves frame JSON, brief, and docx. Program-office priorities from the full "
            "solicitation package — readiness outcome, pain points, and win-theme candidates."
        ),
    },
    {
        "phase": "4",
        "category": "RFP Briefing · Related skill",
        "title": "Acquisition traps",
        "prompt": (
            "Forensic focus: FAR clause traps, Section L/M compliance gaps, "
            "and contracts-shop errors — not program-office readiness."
        ),
        "channel": "briefing_related",
        "parent_slice_id": "mission-readiness",
        "skill": "compliance-auditor",
        "sort_order": 41,
        "label": "Acquisition traps",
    },
    {
        "phase": "4",
        "category": "RFP Briefing · Skill",
        "title": "Financial risk",
        "prompt": (
            "Forensic focus: payment terms and cash-flow timing by CLIN. "
            "Require verbatim extracts, a CLIN cash-flow table, H/M/L risks, and BOE implications."
        ),
        "channel": "briefing_skill",
        "slice_id": "financial",
        "skill": "payment-terms-auditor",
        "sort_order": 50,
        "icon": "banknote",
        "label": "Financial risk",
        "description": (
            "Payment terms, CLIN cash flow, and capital/inventory obligations (forensic skills)."
        ),
    },
    {
        "phase": "4",
        "category": "RFP Briefing · Related skill",
        "title": "Capital obligations",
        "prompt": (
            "Forensic focus: upfront capital, inventory ownership, disposition, "
            "and transition property obligations."
        ),
        "channel": "briefing_related",
        "parent_slice_id": "financial",
        "skill": "capital-obligations-auditor",
        "sort_order": 51,
        "label": "Capital obligations",
    },
    {
        "phase": "4",
        "category": "RFP Briefing · Skill",
        "title": "Logistics SLAs",
        "prompt": (
            "Forensic focus: shipping destinations, on-time delivery, fill rate, "
            "and surge logistics SLAs. Require verbatim extracts and H/M/L risks."
        ),
        "channel": "briefing_skill",
        "slice_id": "logistics",
        "skill": "logistics-sla-auditor",
        "sort_order": 60,
        "icon": "truck",
        "label": "Logistics SLAs",
        "description": (
            "Shipping destinations, OTD/FR metrics, and surge logistics performance standards."
        ),
    },
]

BRIEFING_CHANNELS = frozenset(
    {"briefing_chat", "briefing_skill", "briefing_related", "skill_default"}
)

__all__ = ["BRIEFING_CHANNELS", "BRIEFING_PROMPT_LIBRARY"]