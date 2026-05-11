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
from src.skills.chain_contracts import CONTRACT_REGISTRY

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STEP_SAFE = re.compile(r"[^a-z0-9_-]+")

_EXCLUDED_BY_DEFAULT = {
    "caveman",
    "grill-me",
    "govcon-ontology",
    "improve-codebase-architecture",
    "skill-creator",
    "tdd",
    "to-issues",
    "to-prd",
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

_RENDERER_SKILLS = {"renderers", "huashu-design"}
_RENDER_INTENT_TERMS = {"render", "convert", "export", "format"}
_EXISTING_ARTIFACT_TERMS = {
    "existing",
    "source",
    "artifact",
    "artifacts",
    "markdown",
    "md",
    "json",
    "html",
    "docx",
    "xlsx",
    "pptx",
    "pdf",
    "word",
    "excel",
    "workbook",
    "deck",
    "slides",
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
        contract = CONTRACT_REGISTRY.get(name)
        keywords = set(contract.keywords) if contract else set()
        name_tokens = _tokens(name)
        capability_tokens = _tokens(summary.capability)
        score = 0
        score += 4 * len(tokens & keywords)
        score += 2 * len(tokens & name_tokens)
        score += len(tokens & capability_tokens)
        if contract is None:
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
                downstreams = CONTRACT_REGISTRY.downstream_skills(upstream)
                if CONTRACT_REGISTRY.is_renderable_upstream(upstream) and renderer in downstreams:
                    _append_unique(selected, renderer)

        selected.sort(key=CONTRACT_REGISTRY.phase_rank)
        selected = self._prune_disconnected(selected)
        return selected[:max_steps]

    @staticmethod
    def _target_skills(
        available: dict[str, SkillSummary],
        scores: dict[str, int],
        tokens: set[str],
    ) -> list[str]:
        matched: list[str] = []
        for name in CONTRACT_REGISTRY.names():
            if name in available and scores.get(name, 0) >= 4:
                _append_unique(matched, name)
        render_targets = [name for name in matched if _is_renderer_skill(name)]
        non_render_targets = [name for name in matched if not _is_renderer_skill(name)]
        targets: list[str]
        if render_targets and _is_explicit_render_request(tokens):
            targets = render_targets
        elif non_render_targets:
            # Rendering is an append step, not an outcome planner target, when a
            # content-producing skill already matches the request.
            targets = non_render_targets
        elif render_targets:
            fallback = SkillChainPlanner._best_non_render_match(available, scores)
            targets = [fallback] if fallback else render_targets
        else:
            targets = []
        if _needs_rendering(tokens):
            for name in ["proposal-generator", "price-to-win", "subcontractor-sow-builder"]:
                if name in available and scores.get(name, 0) >= 4:
                    _append_unique(targets, name)
        if not targets:
            best = max(scores.items(), key=lambda item: item[1], default=("", 0))
            if best[0] and best[1] > 0:
                targets.append(best[0])
        targets.sort(key=lambda name: (CONTRACT_REGISTRY.phase_rank(name), -scores.get(name, 0)))
        # Prefer latest-phase matched target as outcome, but retain explicitly matched independent goals.
        if len(targets) > 1:
            last_rank = max(CONTRACT_REGISTRY.phase_rank(name) for name in targets)
            late = [name for name in targets if CONTRACT_REGISTRY.phase_rank(name) == last_rank]
            early = [
                name for name in targets
                if any(name in CONTRACT_REGISTRY.downstream_skills(candidate) for candidate in targets)
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
        for candidate in CONTRACT_REGISTRY.upstream_skills(target):
            if candidate not in available:
                continue
            score = scores.get(candidate, 0)
            if score >= 4 or _default_upstream(candidate, target, tokens):
                upstreams.extend(
                    SkillChainPlanner._matched_upstreams(candidate, available, scores, tokens)
                )
                _append_unique(upstreams, candidate)
        upstreams.sort(key=CONTRACT_REGISTRY.phase_rank)
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
    def _best_non_render_match(
        available: dict[str, SkillSummary],
        scores: dict[str, int],
    ) -> str:
        eligible = [
            (name, score)
            for name, score in scores.items()
            if name in available and not _is_renderer_skill(name) and score > 0
        ]
        eligible.sort(key=lambda item: (-item[1], CONTRACT_REGISTRY.phase_rank(item[0])))
        return eligible[0][0] if eligible else ""

    @staticmethod
    def _prune_disconnected(selected: list[str]) -> list[str]:
        if len(selected) <= 1:
            return selected
        pruned: list[str] = []
        for index, name in enumerate(selected):
            if not pruned:
                pruned.append(name)
                continue
            has_prev_edge = any(name in CONTRACT_REGISTRY.downstream_skills(prev) for prev in pruned)
            has_next_edge = any(
                downstream in CONTRACT_REGISTRY.downstream_skills(name)
                for downstream in selected[index + 1 :]
            )
            direct_goal = not CONTRACT_REGISTRY.has(name)
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
                if name in CONTRACT_REGISTRY.downstream_skills(prev)
            ]
            requirements = [
                ChainArtifactRequirement(
                    id=f"{dep}-handoff",
                    description=f"Use artifacts from {dep} when useful for {name}.",
                    from_steps=[dep],
                    products=_edge_products(selected, step_ids, dep),
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
                        "retrieval_focus": _retrieval_focus(name),
                        "retrieval_query": _retrieval_query(name, prompt, outcome or prompt),
                        "ask_for_input_when_missing": True,
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
                "retrieval_strategy": "step-scoped-hints",
                "hitl_mode": "resume-after-missing-input",
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
        contract = CONTRACT_REGISTRY.get(name)
        hits = sorted(tokens & set(contract.keywords if contract else frozenset()))
        if hits:
            return "Matched goal terms: " + ", ".join(hits[:8])
        if any(next_name in CONTRACT_REGISTRY.downstream_skills(name) for next_name in selected):
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


def _is_renderer_skill(skill: str) -> bool:
    return skill in _RENDERER_SKILLS


def _is_explicit_render_request(tokens: set[str]) -> bool:
    return bool(tokens & _RENDER_INTENT_TERMS) and bool(tokens & _EXISTING_ARTIFACT_TERMS)


def _default_upstream(candidate: str, target: str, tokens: set[str]) -> bool:
    return CONTRACT_REGISTRY.default_upstream(candidate, target, tokens)


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
    return CONTRACT_REGISTRY.role(skill) or "perform directly matched skill work"


def _quality_gate(skill: str, expected_outcome: str) -> str:
    return CONTRACT_REGISTRY.quality_gate(skill, expected_outcome)


def _retrieval_focus(skill: str) -> list[str]:
    contract = CONTRACT_REGISTRY.get(skill)
    if contract is None:
        return []
    focus: list[str] = []
    seen: set[str] = set()
    for bucket in (contract.accepts, contract.produces, contract.keywords):
        for item in sorted(bucket):
            if item not in seen:
                seen.add(item)
                focus.append(item)
            if len(focus) >= 8:
                return focus
    return focus


def _retrieval_query(skill: str, prompt: str, expected_outcome: str) -> str:
    contract = CONTRACT_REGISTRY.get(skill)
    role = _role_for(skill)
    focus = ", ".join(_retrieval_focus(skill))
    if contract is None:
        return f"{prompt.strip()} Focus on {role}."
    if focus:
        return (
            f"{prompt.strip()} Focus on {role}. Prioritize evidence related to: "
            f"{focus}. Target outcome: {expected_outcome.strip()}."
        )
    return f"{prompt.strip()} Focus on {role}. Target outcome: {expected_outcome.strip()}."


def _edge_extensions(
    selected: list[str],
    step_ids: dict[str, str],
    dep_step_id: str,
) -> list[str]:
    inverse = {step_id: skill for skill, step_id in step_ids.items()}
    upstream = inverse.get(dep_step_id, "")
    return list(CONTRACT_REGISTRY.artifact_extensions(upstream))


def _edge_products(
    selected: list[str],
    step_ids: dict[str, str],
    dep_step_id: str,
) -> list[str]:
    inverse = {step_id: skill for skill, step_id in step_ids.items()}
    upstream = inverse.get(dep_step_id, "")
    contract = CONTRACT_REGISTRY.get(upstream)
    return sorted(contract.produces) if contract else []


__all__ = ["ChainPlan", "PlannedSkill", "SkillChainPlanner"]
