"""Skill family / role resolution and chain enrichment for the Skills UI."""

from __future__ import annotations

import re
from typing import Any, Mapping

from src.skills.chain_contracts import CONTRACT_REGISTRY
from src.skills.skill_models import Skill

_ALLOWED_SKILL_ROLES = frozenset({"standalone", "slice", "orchestrator"})

_FAMILY_LABELS: dict[str, str] = {
    "readiness-frame": "Mission Readiness Frame",
    "pricing": "Pricing & Workload",
    "proposal-pipeline": "Proposal Pipeline",
    "compliance": "Compliance & Risk",
    "capture-intel": "Capture Intelligence",
}

_FAMILY_PREFIX_RULES: tuple[tuple[str, str], ...] = (
    ("readiness-frame-", "readiness-frame"),
)

_ORCHESTRATOR_SKILLS = frozenset(
    {
        "mission-readiness-framer",
        "proposal-generator",
    }
)

_HANDOFF_SUFFIX = re.compile(r"_handoff$")


def _meta(skill: Skill) -> Mapping[str, Any]:
    return skill.frontmatter.metadata or {}


def resolve_skill_role(skill: Skill) -> str:
    """Return standalone | slice | orchestrator."""
    meta = _meta(skill)
    explicit = str(meta.get("skill_role") or "").strip().lower()
    if explicit in _ALLOWED_SKILL_ROLES:
        return explicit
    if skill.name in _ORCHESTRATOR_SKILLS:
        return "orchestrator"
    contract = CONTRACT_REGISTRY.get(skill.name)
    if contract is not None:
        handoff_accepts = sum(
            1 for product in contract.accepts if _HANDOFF_SUFFIX.search(product)
        )
        if handoff_accepts >= 2 or (
            len(contract.accepts) >= 3 and skill.name.endswith("-framer")
        ):
            return "orchestrator"
    for prefix, _family in _FAMILY_PREFIX_RULES:
        if skill.name.startswith(prefix):
            return "slice"
    return "standalone"


def resolve_skill_family(skill: Skill) -> str:
    """Return family slug or empty string for ungrouped skills."""
    meta = _meta(skill)
    explicit = str(meta.get("skill_family") or "").strip().lower()
    if explicit:
        return explicit
    for prefix, family in _FAMILY_PREFIX_RULES:
        if skill.name.startswith(prefix):
            return family
    if skill.name in {"workload-analyzer", "price-to-win"}:
        return "pricing"
    if skill.name in {"proposal-generator", "subcontractor-sow-builder"}:
        return "proposal-pipeline"
    if skill.name in {"compliance-auditor", "oci-sweeper", "payment-terms-auditor"}:
        return "compliance"
    if skill.name == "competitive-intel":
        return "capture-intel"
    if skill.name == "mission-readiness-framer":
        return "readiness-frame"
    return ""


def resolve_skill_family_label(skill: Skill, *, family: str = "") -> str:
    """Human label for a skill family section."""
    meta = _meta(skill)
    explicit = str(meta.get("skill_family_label") or "").strip()
    if explicit:
        return explicit
    slug = family or resolve_skill_family(skill)
    if slug:
        return _FAMILY_LABELS.get(slug, slug.replace("-", " ").title())
    return ""


def chain_summary_for_skill(skill_name: str) -> dict[str, Any]:
    """Planner-facing chain edges for one skill."""
    contract = CONTRACT_REGISTRY.get(skill_name)
    if contract is None:
        return {
            "registered": False,
            "accepts": [],
            "produces": [],
            "upstream_skills": [],
            "downstream_skills": [],
            "role": "",
            "phase_rank": 60,
        }
    return {
        "registered": True,
        "accepts": sorted(contract.accepts),
        "produces": sorted(contract.produces),
        "upstream_skills": sorted(CONTRACT_REGISTRY.upstream_skills(skill_name)),
        "downstream_skills": sorted(contract.downstream_skills),
        "role": contract.role,
        "phase_rank": contract.phase_rank,
    }


def orchestrator_compiles_label(skill: Skill) -> str:
    """Short subtitle: which handoff families an orchestrator accepts."""
    contract = CONTRACT_REGISTRY.get(skill.name)
    if contract is None or not contract.accepts:
        return ""
    handoffs = [p for p in sorted(contract.accepts) if _HANDOFF_SUFFIX.search(p)]
    if handoffs:
        return ", ".join(handoffs)
    return ", ".join(sorted(contract.accepts)[:6])


def enrich_skill_summary(skill: Skill) -> dict[str, Any]:
    """Extend catalog summary with grouping + chain metadata for the UI."""
    summary = skill.to_summary()
    family = resolve_skill_family(skill)
    role = resolve_skill_role(skill)
    chain = chain_summary_for_skill(skill.name)
    summary.update(
        {
            "skill_role": role,
            "skill_family": family,
            "skill_family_label": resolve_skill_family_label(skill, family=family),
            "chain": chain,
            "orchestrator_compiles": (
                orchestrator_compiles_label(skill) if role == "orchestrator" else ""
            ),
        }
    )
    return summary