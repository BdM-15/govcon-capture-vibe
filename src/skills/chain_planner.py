"""Deterministic planner for logical Theseus skill chains."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from src.skills.chain_models import (
    ChainArtifactRequirement,
    ChainSpec,
    ChainStepSpec,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STEP_SAFE = re.compile(r"[^a-z0-9_-]+")

_EXCLUDED_BY_DEFAULT = {
    "caveman",
    "grill-me",
    "grill-me-bid-strategy",
    "grill-me-capture",
    "grill-me-govcon",
    "grill-me-proposal",
    "grill-me-ptw",
    "govcon-ontology",
    "improve-codebase-architecture",
    "skill-creator",
    "tdd",
    "to-issues",
    "to-prd",
}

_PHASE_RANK = {
    "competitive-intel": 10,
    "rfp-reverse-engineer": 15,
    "workload-analyzer": 20,
    "data-analyzer": 20,
    "compliance-auditor": 30,
    "oci-sweeper": 30,
    "ot-prototype-strategist": 35,
    "price-to-win": 40,
    "proposal-generator": 50,
    "subcontractor-sow-builder": 50,
    "renderers": 80,
    "huashu-design": 85,
}

_OUTPUT_TERMS = {
    "docx",
    "document",
    "word",
    "xlsx",
    "workbook",
    "spreadsheet",
    "pptx",
    "slides",
    "pdf",
    "html",
    "deliverable",
    "artifact",
    "package",
}

_CONTRACTS: dict[str, dict[str, Any]] = {
    "competitive-intel": {
        "keywords": {
            "competitor", "competitive", "incumbent", "award", "awards",
            "obligation", "obligations", "idiq", "order", "orders", "burn",
            "black", "hat", "contract", "naics", "psc",
        },
        "produces": {"competitor_intel", "award_history", "obligation_data"},
        "extensions": ["json", "md", "html", "docx", "xlsx"],
    },
    "workload-analyzer": {
        "keywords": {
            "workload", "site", "sites", "staffing", "labor", "volume",
            "demand", "section", "spreadsheet", "clin", "hours", "attachment",
        },
        "produces": {"workload_handoff", "pricing_inputs"},
        "extensions": ["json", "xlsx", "md"],
    },
    "rfp-reverse-engineer": {
        "keywords": {
            "reverse", "engineer", "scope", "hot", "button", "buttons",
            "hidden", "decision", "tree", "pws", "sow", "qasp", "trap",
        },
        "produces": {"strategy_handoff", "scope_read"},
        "extensions": ["json", "md", "html"],
    },
    "compliance-auditor": {
        "keywords": {
            "compliance", "audit", "far", "dfars", "clause", "clauses",
            "shall", "l", "m", "matrix", "instruction", "evaluation",
        },
        "produces": {"compliance_findings", "gap_list"},
        "extensions": ["json", "md", "xlsx", "docx"],
    },
    "oci-sweeper": {
        "keywords": {"oci", "conflict", "impaired", "objectivity", "unequal", "access"},
        "produces": {"oci_findings"},
        "extensions": ["json", "md", "docx"],
    },
    "price-to-win": {
        "keywords": {
            "price", "pricing", "ptw", "cost", "costing", "estimate",
            "should", "wrap", "rate", "rates", "labor", "boe", "target",
        },
        "produces": {"pricing_stack", "ptw_workbook"},
        "extensions": ["json", "xlsx", "md", "docx"],
    },
    "ot-prototype-strategist": {
        "keywords": {"ot", "prototype", "trl", "milestone", "cost", "share", "4022", "4021"},
        "produces": {"ot_strategy", "prototype_cost_stack"},
        "extensions": ["json", "xlsx", "md"],
    },
    "proposal-generator": {
        "keywords": {
            "proposal", "respond", "response", "draft", "outline", "volume",
            "executive", "summary", "theme", "themes", "fab", "matrix",
        },
        "produces": {"proposal_draft", "compliance_matrix"},
        "extensions": ["json", "md", "html", "docx", "xlsx"],
    },
    "subcontractor-sow-builder": {
        "keywords": {"subcontractor", "sub", "teaming", "partner", "sow", "pws"},
        "produces": {"sub_sow", "sub_pws"},
        "extensions": ["md", "docx"],
    },
    "renderers": {
        "keywords": {"render", "docx", "word", "xlsx", "excel", "workbook"},
        "produces": {"docx", "xlsx"},
        "extensions": ["md", "json"],
    },
    "huashu-design": {
        "keywords": {"slides", "pptx", "pdf", "html", "deck", "prototype", "visual"},
        "produces": {"presentation", "html", "pdf"},
        "extensions": ["html", "json", "md"],
    },
}

_HANDOFFS: dict[str, set[str]] = {
    "competitive-intel": {"price-to-win", "proposal-generator"},
    "workload-analyzer": {"price-to-win", "proposal-generator"},
    "rfp-reverse-engineer": {"proposal-generator"},
    "compliance-auditor": {"proposal-generator"},
    "oci-sweeper": {"proposal-generator"},
    "price-to-win": {"proposal-generator", "renderers"},
    "ot-prototype-strategist": {"proposal-generator", "renderers"},
    "proposal-generator": {"renderers", "huashu-design"},
    "subcontractor-sow-builder": {"renderers"},
}

_RENDERABLE_UPSTREAM = {
    "proposal-generator",
    "price-to-win",
    "subcontractor-sow-builder",
    "ot-prototype-strategist",
}


class PlannedSkill(BaseModel):
    """One selected or rejected planner candidate."""

    model_config = ConfigDict(extra="forbid")

    skill: str
    score: int = 0
    role: str = ""
    reason: str = ""


class ChainPlan(BaseModel):
    """Planner output envelope."""

    model_config = ConfigDict(extra="forbid")

    spec: ChainSpec
    selected_skills: list[PlannedSkill] = Field(default_factory=list)
    rejected_skills: list[PlannedSkill] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rationale: str = ""
    iteration_policy: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class SkillSummary:
    name: str
    description: str
    capability: str = ""
    runtime_mode: str = ""


class SkillChainPlanner:
    """Build logical chain specs from goal text and installed skill contracts."""

    def __init__(self, skills: Iterable[dict[str, Any]]) -> None:
        self._skills = {summary.name: summary for summary in map(self._summary, skills)}

    def plan(
        self,
        *,
        prompt: str,
        outcome: str = "",
        max_steps: int = 8,
        include_rendering: bool = True,
    ) -> ChainPlan:
        goal = " ".join(part for part in [prompt, outcome] if part).strip()
        tokens = _tokens(goal)
        available = {
            name: summary
            for name, summary in self._skills.items()
            if self._is_eligible(name, tokens)
        }
        scores = {
            name: self._score(summary, tokens)
            for name, summary in available.items()
        }
        selected = self._select_skills(
            available,
            scores,
            tokens,
            max_steps=max_steps,
            include_rendering=include_rendering,
        )
        warnings: list[str] = []
        if not selected:
            fallback = self._best_direct_match(available, scores)
            if fallback:
                selected = [fallback]
                warnings.append("Planner found no full handoff path; using best direct skill match.")
            else:
                raise ValueError("No installed skill matches chain goal")

        selected = selected[:max(1, max_steps)]
        spec = self._build_spec(selected, prompt=prompt, outcome=outcome, tokens=tokens)
        selected_rows = [
            PlannedSkill(
                skill=name,
                score=scores.get(name, 0),
                role=_role_for(name),
                reason=self._reason_for(name, tokens, selected),
            )
            for name in selected
        ]
        rejected_rows = [
            PlannedSkill(
                skill=name,
                score=score,
                role=_role_for(name),
                reason="No compatible handoff path into selected outcome.",
            )
            for name, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
            if name not in selected and score > 0
        ][:10]
        return ChainPlan(
            spec=spec,
            selected_skills=selected_rows,
            rejected_skills=rejected_rows,
            warnings=warnings,
            rationale=self._rationale(selected),
            iteration_policy={
                "mode": "outcome-gated-linear",
                "max_revisions_per_step": 1,
                "expected_outcome": outcome or prompt,
                "note": "Planner encodes quality gates and handoff contracts; runtime resume/rerun handles corrective iteration.",
            },
        )

    @staticmethod
    def _summary(raw: dict[str, Any]) -> SkillSummary:
        return SkillSummary(
            name=str(raw.get("name") or ""),
            description=str(raw.get("description") or ""),
            capability=str(raw.get("capability") or raw.get("category") or ""),
            runtime_mode=str(raw.get("runtime_mode") or ""),
        )

    @staticmethod
    def _is_eligible(name: str, tokens: set[str]) -> bool:
        if name not in _EXCLUDED_BY_DEFAULT:
            return True
        name_tokens = _tokens(name)
        return bool(name_tokens & tokens)

    @staticmethod
    def _score(summary: SkillSummary, tokens: set[str]) -> int:
        name = summary.name
        contract = _CONTRACTS.get(name, {})
        keywords = set(contract.get("keywords") or set())
        name_tokens = _tokens(name)
        capability_tokens = _tokens(summary.capability)
        score = 0
        score += 4 * len(tokens & keywords)
        score += 2 * len(tokens & name_tokens)
        score += len(tokens & capability_tokens)
        if not contract:
            text_tokens = _tokens(summary.description)
            score += min(len(tokens & text_tokens), 3)
        if summary.capability in {"research", "analyze", "audit", "estimate", "draft", "render"}:
            score += 1
        return score

    def _select_skills(
        self,
        available: dict[str, SkillSummary],
        scores: dict[str, int],
        tokens: set[str],
        *,
        max_steps: int,
        include_rendering: bool,
    ) -> list[str]:
        targets = self._target_skills(available, scores, tokens)
        selected: list[str] = []
        for target in targets:
            for upstream in self._matched_upstreams(target, available, scores, tokens):
                _append_unique(selected, upstream)
            _append_unique(selected, target)

        if include_rendering and _needs_rendering(tokens):
            renderer = self._renderer_for(tokens, available)
            if renderer and selected and selected[-1] != renderer:
                upstream = selected[-1]
                if upstream in _RENDERABLE_UPSTREAM and renderer in _HANDOFFS.get(upstream, set()):
                    _append_unique(selected, renderer)

        selected.sort(key=lambda name: _PHASE_RANK.get(name, 60))
        selected = self._prune_disconnected(selected)
        return selected[:max_steps]

    @staticmethod
    def _target_skills(
        available: dict[str, SkillSummary],
        scores: dict[str, int],
        tokens: set[str],
    ) -> list[str]:
        targets: list[str] = []
        for name in _CONTRACTS:
            if name in available and scores.get(name, 0) >= 4:
                _append_unique(targets, name)
        if _needs_rendering(tokens):
            for name in ["proposal-generator", "price-to-win", "subcontractor-sow-builder"]:
                if name in available and scores.get(name, 0) >= 4:
                    _append_unique(targets, name)
        if not targets:
            best = max(scores.items(), key=lambda item: item[1], default=("", 0))
            if best[0] and best[1] > 0:
                targets.append(best[0])
        targets.sort(key=lambda name: (_PHASE_RANK.get(name, 60), -scores.get(name, 0)))
        # Prefer latest-phase matched target as outcome, but retain explicitly matched independent goals.
        if len(targets) > 1:
            last_rank = max(_PHASE_RANK.get(name, 60) for name in targets)
            late = [name for name in targets if _PHASE_RANK.get(name, 60) == last_rank]
            early = [
                name for name in targets
                if any(name in _HANDOFFS.get(candidate, set()) for candidate in targets)
            ]
            return [*early, *late]
        return targets

    @staticmethod
    def _matched_upstreams(
        target: str,
        available: dict[str, SkillSummary],
        scores: dict[str, int],
        tokens: set[str],
    ) -> list[str]:
        upstreams: list[str] = []
        for candidate, downstreams in _HANDOFFS.items():
            if target not in downstreams or candidate not in available:
                continue
            score = scores.get(candidate, 0)
            if score >= 4 or _default_upstream(candidate, target, tokens):
                upstreams.extend(
                    SkillChainPlanner._matched_upstreams(candidate, available, scores, tokens)
                )
                _append_unique(upstreams, candidate)
        upstreams.sort(key=lambda name: _PHASE_RANK.get(name, 60))
        return upstreams

    @staticmethod
    def _renderer_for(tokens: set[str], available: dict[str, SkillSummary]) -> str:
        if {"pptx", "slides", "pdf", "html", "deck", "visual"} & tokens:
            if "huashu-design" in available:
                return "huashu-design"
        if "renderers" in available:
            return "renderers"
        return ""

    @staticmethod
    def _best_direct_match(
        available: dict[str, SkillSummary],
        scores: dict[str, int],
    ) -> str:
        eligible = [(name, score) for name, score in scores.items() if name in available]
        eligible.sort(key=lambda item: item[1], reverse=True)
        return eligible[0][0] if eligible and eligible[0][1] > 0 else ""

    @staticmethod
    def _prune_disconnected(selected: list[str]) -> list[str]:
        if len(selected) <= 1:
            return selected
        pruned: list[str] = []
        for index, name in enumerate(selected):
            if not pruned:
                pruned.append(name)
                continue
            has_prev_edge = any(name in _HANDOFFS.get(prev, set()) for prev in pruned)
            has_next_edge = any(
                downstream in _HANDOFFS.get(name, set())
                for downstream in selected[index + 1 :]
            )
            direct_goal = name not in _CONTRACTS
            if has_prev_edge or has_next_edge or direct_goal:
                pruned.append(name)
        return pruned

    def _build_spec(
        self,
        selected: list[str],
        *,
        prompt: str,
        outcome: str,
        tokens: set[str],
    ) -> ChainSpec:
        step_ids: dict[str, str] = {}
        steps: list[ChainStepSpec] = []
        for index, name in enumerate(selected, start=1):
            step_id = _step_id(name, step_ids.values())
            step_ids[name] = step_id
            deps = [
                step_ids[prev]
                for prev in selected[: index - 1]
                if name in _HANDOFFS.get(prev, set())
            ]
            requirements = [
                ChainArtifactRequirement(
                    id=f"{dep}-handoff",
                    description=f"Use artifacts from {dep} when useful for {name}.",
                    from_steps=[dep],
                    extensions=_edge_extensions(selected, step_ids, dep),
                    required=False,
                )
                for dep in deps
            ]
            steps.append(
                ChainStepSpec(
                    id=step_id,
                    skill=name,
                    prompt=self._step_prompt(name, prompt=prompt, outcome=outcome),
                    depends_on=deps,
                    artifact_requirements=requirements,
                    context={
                        "planner_role": _role_for(name),
                        "expected_outcome": outcome or prompt,
                        "quality_gate": _quality_gate(name, outcome or prompt),
                    },
                )
            )
        name = _chain_name(selected, tokens)
        return ChainSpec(
            name=name,
            prompt=prompt,
            context={
                "planner": "deterministic-skill-chain-planner",
                "expected_outcome": outcome or prompt,
                "quality_gates": [
                    {"skill": name, "gate": _quality_gate(name, outcome or prompt)}
                    for name in selected
                ],
            },
            steps=steps,
        )

    @staticmethod
    def _step_prompt(name: str, *, prompt: str, outcome: str) -> str:
        gate = _quality_gate(name, outcome or prompt)
        return (
            f"User goal: {prompt.strip()}\n"
            f"Expected outcome: {(outcome or prompt).strip()}\n"
            f"Chain role: {_role_for(name)}\n"
            f"Quality gate: {gate}\n"
            "Use Theseus Chain Handoff JSON for upstream artifacts and context. "
            "If output cannot satisfy the quality gate, state exact gaps and produce the best partial artifact."
        )

    @staticmethod
    def _reason_for(name: str, tokens: set[str], selected: list[str]) -> str:
        contract = _CONTRACTS.get(name, {})
        hits = sorted(tokens & set(contract.get("keywords") or set()))
        if hits:
            return "Matched goal terms: " + ", ".join(hits[:8])
        if any(next_name in _HANDOFFS.get(name, set()) for next_name in selected):
            return "Selected as logical upstream handoff."
        return "Selected as best direct skill match."

    @staticmethod
    def _rationale(selected: list[str]) -> str:
        if len(selected) == 1:
            return f"Single-skill chain: {selected[0]} directly matches requested outcome."
        return " -> ".join(selected) + " selected from compatible handoff graph."


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _needs_rendering(tokens: set[str]) -> bool:
    return bool(tokens & _OUTPUT_TERMS)


def _default_upstream(candidate: str, target: str, tokens: set[str]) -> bool:
    if target == "proposal-generator" and candidate == "rfp-reverse-engineer":
        return bool({"proposal", "respond", "response", "draft"} & tokens)
    if target == "price-to-win" and candidate == "competitive-intel":
        return bool({"price", "pricing", "ptw", "incumbent", "competitor"} & tokens)
    return False


def _step_id(skill: str, existing: Iterable[str]) -> str:
    base = _STEP_SAFE.sub("-", skill.lower()).strip("-")[:48] or "step"
    used = set(existing)
    if base not in used:
        return base
    suffix = 2
    while f"{base}-{suffix}" in used:
        suffix += 1
    return f"{base}-{suffix}"


def _chain_name(selected: list[str], tokens: set[str]) -> str:
    if {"price", "pricing", "ptw"} & tokens:
        return "price-to-win-chain"
    if {"proposal", "respond", "response", "draft"} & tokens:
        return "proposal-chain"
    if {"compliance", "far", "dfars"} & tokens:
        return "compliance-chain"
    if len(selected) == 1:
        return selected[0]
    return "-to-".join([selected[0], selected[-1]])[:128]


def _role_for(skill: str) -> str:
    return {
        "competitive-intel": "research competitor, incumbent, and obligation context",
        "workload-analyzer": "turn workload data into pricing inputs",
        "rfp-reverse-engineer": "extract hidden scope and strategy signals",
        "compliance-auditor": "audit instructions, clauses, and compliance gaps",
        "oci-sweeper": "surface OCI risk and mitigation notes",
        "price-to-win": "build price-to-win / should-cost estimate",
        "ot-prototype-strategist": "build OT prototype strategy and milestone cost stack",
        "proposal-generator": "draft proposal response artifacts from upstream evidence",
        "subcontractor-sow-builder": "draft downstream SOW/PWS artifact",
        "renderers": "render structured source artifacts into Office deliverables",
        "huashu-design": "render visual/presentation deliverables",
    }.get(skill, "perform directly matched skill work")


def _quality_gate(skill: str, expected_outcome: str) -> str:
    target = expected_outcome.strip() or "requested outcome"
    return f"Output must advance '{target}' and name any missing upstream inputs."


def _edge_extensions(
    selected: list[str],
    step_ids: dict[str, str],
    dep_step_id: str,
) -> list[str]:
    inverse = {step_id: skill for skill, step_id in step_ids.items()}
    upstream = inverse.get(dep_step_id, "")
    return list(_CONTRACTS.get(upstream, {}).get("extensions") or ["json", "md"])


__all__ = ["ChainPlan", "PlannedSkill", "SkillChainPlanner"]
