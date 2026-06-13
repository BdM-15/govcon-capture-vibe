"""Machine-readable contracts for chainable Theseus skills."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SAFE_SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")
_SAFE_PRODUCT_NAME = re.compile(r"^[a-z][a-z0-9_/-]{0,127}$")


def _normalized_words(values: Iterable[str]) -> frozenset[str]:
    return frozenset(str(value).strip().lower() for value in values if str(value).strip())


def _normalized_products(values: Iterable[str]) -> frozenset[str]:
    return frozenset(
        str(value).strip().lower()
        for value in values
        if str(value).strip()
    )


class SkillChainContract(BaseModel):
    """Planner-facing promise for one chainable skill."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    skill: str = Field(..., min_length=1, max_length=128)
    keywords: frozenset[str] = Field(default_factory=frozenset)
    accepts: frozenset[str] = Field(default_factory=frozenset)
    produces: frozenset[str] = Field(default_factory=frozenset)
    artifact_extensions: tuple[str, ...] = ("json", "md")
    downstream_skills: frozenset[str] = Field(default_factory=frozenset)
    phase_rank: int = Field(60, ge=0, le=100)
    role: str = ""
    quality_gate: str = ""
    renderable: bool = False
    default_upstream_triggers: dict[str, frozenset[str]] = Field(default_factory=dict)

    @field_validator("skill")
    @classmethod
    def _validate_skill(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _SAFE_SKILL_NAME.fullmatch(normalized):
            raise ValueError("skill must be lowercase alphanumeric with hyphen/underscore separators")
        return normalized

    @field_validator("keywords", "downstream_skills", mode="before")
    @classmethod
    def _validate_words(cls, value: Iterable[str] | None) -> frozenset[str]:
        return _normalized_words(value or [])

    @field_validator("accepts", "produces", mode="before")
    @classmethod
    def _validate_products(cls, value: Iterable[str] | None) -> frozenset[str]:
        products = _normalized_products(value or [])
        invalid = [product for product in products if not _SAFE_PRODUCT_NAME.fullmatch(product)]
        if invalid:
            raise ValueError(f"invalid product name(s): {', '.join(sorted(invalid))}")
        return products

    @field_validator("artifact_extensions", mode="before")
    @classmethod
    def _validate_extensions(cls, value: Iterable[str] | None) -> tuple[str, ...]:
        extensions = tuple(
            str(extension).strip().lower().lstrip(".")
            for extension in (value or [])
            if str(extension).strip()
        )
        return extensions or ("json", "md")

    @field_validator("default_upstream_triggers", mode="before")
    @classmethod
    def _validate_default_triggers(
        cls,
        value: dict[str, Iterable[str]] | None,
    ) -> dict[str, frozenset[str]]:
        if not value:
            return {}
        return {
            skill.strip().lower(): _normalized_words(triggers)
            for skill, triggers in value.items()
            if skill.strip()
        }

    @model_validator(mode="after")
    def _validate_edges(self) -> "SkillChainContract":
        invalid_downstreams = [
            downstream
            for downstream in self.downstream_skills
            if not _SAFE_SKILL_NAME.fullmatch(downstream)
        ]
        invalid_defaults = [
            downstream
            for downstream in self.default_upstream_triggers
            if not _SAFE_SKILL_NAME.fullmatch(downstream)
        ]
        invalid = sorted({*invalid_downstreams, *invalid_defaults})
        if invalid:
            raise ValueError(f"invalid downstream skill name(s): {', '.join(invalid)}")
        return self


class SkillContractRegistry:
    """Lookup surface for chain planner contracts."""

    def __init__(self, contracts: Iterable[SkillChainContract]) -> None:
        indexed: dict[str, SkillChainContract] = {}
        for contract in contracts:
            if contract.skill in indexed:
                raise ValueError(f"duplicate skill chain contract: {contract.skill}")
            indexed[contract.skill] = contract
        self._contracts = indexed

    def __contains__(self, skill: str) -> bool:
        return skill in self._contracts

    def __iter__(self) -> Iterator[SkillChainContract]:
        return iter(self._contracts.values())

    def get(self, skill: str) -> SkillChainContract | None:
        return self._contracts.get(skill)

    def require(self, skill: str) -> SkillChainContract:
        contract = self.get(skill)
        if contract is None:
            raise KeyError(f"missing skill chain contract: {skill}")
        return contract

    def has(self, skill: str) -> bool:
        return skill in self._contracts

    def names(self) -> tuple[str, ...]:
        return tuple(self._contracts)

    def downstream_skills(self, skill: str) -> frozenset[str]:
        contract = self.get(skill)
        return contract.downstream_skills if contract else frozenset()

    def upstream_skills(self, target: str) -> tuple[str, ...]:
        return tuple(
            contract.skill
            for contract in self._contracts.values()
            if target in contract.downstream_skills
        )

    def phase_rank(self, skill: str) -> int:
        contract = self.get(skill)
        return contract.phase_rank if contract else 60

    def role(self, skill: str) -> str:
        contract = self.get(skill)
        return contract.role if contract else ""

    def artifact_extensions(self, skill: str) -> tuple[str, ...]:
        contract = self.get(skill)
        return contract.artifact_extensions if contract else ("json", "md")

    def is_renderable_upstream(self, skill: str) -> bool:
        contract = self.get(skill)
        return bool(contract and contract.renderable)

    def default_upstream(self, candidate: str, target: str, tokens: set[str]) -> bool:
        contract = self.get(candidate)
        if not contract:
            return False
        triggers = contract.default_upstream_triggers.get(target, frozenset())
        return bool(triggers & tokens)

    def quality_gate(self, skill: str, expected_outcome: str) -> str:
        contract = self.get(skill)
        target = expected_outcome.strip() or "requested outcome"
        if contract and contract.quality_gate:
            return f"{contract.quality_gate} Expected outcome: '{target}'."
        return f"Output must advance '{target}' and name any missing upstream inputs."


_DEFAULT_CONTRACTS = [
    SkillChainContract(
        skill="competitive-intel",
        keywords={
            "competitor", "competitive", "incumbent", "award", "awards",
            "obligation", "obligations", "idiq", "order", "orders", "burn",
            "black", "hat", "contract", "naics", "psc",
        },
        accepts=set(),
        produces={"competitor_intel", "award_history", "obligation_data"},
        artifact_extensions=("json", "md", "html", "docx", "xlsx"),
        downstream_skills={"price-to-win", "proposal-generator"},
        phase_rank=10,
        role="research competitor, incumbent, and obligation context",
        quality_gate="Output must identify sources, award/order scope, obligation totals, and missing award-history gaps.",
        default_upstream_triggers={
            "price-to-win": {"price", "pricing", "ptw", "incumbent", "competitor"},
        },
    ),
    SkillChainContract(
        skill="readiness-frame-eval",
        keywords={"evaluation", "factor", "subfactor", "section m", "crosswalk", "eval"},
        accepts={"requirement_graph"},
        produces={"eval_handoff", "evaluation_factors"},
        artifact_extensions=("json",),
        downstream_skills={"mission-readiness-framer"},
        phase_rank=12,
        role="retrieve and structure evaluation factor cross-walk evidence",
        quality_gate="Output must include one eval_crosswalk row per material factor/subfactor with citations.",
    ),
    SkillChainContract(
        skill="readiness-frame-workload",
        keywords={"workload", "pws", "sow", "qasp", "background", "transition", "package"},
        accepts={"requirement_graph"},
        produces={"workload_handoff", "scope_read"},
        artifact_extensions=("json",),
        downstream_skills={"mission-readiness-framer"},
        phase_rank=12,
        role="retrieve package-mechanics evidence for readiness enablers",
        quality_gate="Output must define workload enablers and readiness outcome with cited scope clusters.",
    ),
    SkillChainContract(
        skill="readiness-frame-pains",
        keywords={"pain", "pains", "customer", "challenge", "latent", "structural"},
        accepts={"workload_handoff"},
        produces={"pains_handoff"},
        artifact_extensions=("json",),
        downstream_skills={"mission-readiness-framer"},
        phase_rank=13,
        role="extract Shipley customer pain points from solicitation evidence",
        quality_gate="Output must list material customer pains with rationale and source_chunk_ids.",
    ),
    SkillChainContract(
        skill="readiness-frame-modernization",
        keywords={"modernization", "innovation", "methods", "systems", "tools", "digital"},
        accepts={"workload_handoff"},
        produces={"modernization_handoff"},
        artifact_extensions=("json",),
        downstream_skills={"mission-readiness-framer"},
        phase_rank=13,
        role="map current methods and innovation opportunities in scope",
        quality_gate="Output must cite PWS/QASP evidence for current_methods and innovation_opportunities.",
    ),
    SkillChainContract(
        skill="readiness-frame-tea-leaves",
        keywords={"tea", "leaves", "implicit", "importance", "signal", "hot", "button"},
        accepts={"eval_handoff", "workload_handoff"},
        produces={"tea_leaves_handoff"},
        artifact_extensions=("json",),
        downstream_skills={"mission-readiness-framer"},
        phase_rank=13,
        role="surface importance signals and implicit criteria with alternate reads",
        quality_gate="Output must include importance_signals and implicit_criteria with source citations.",
    ),
    SkillChainContract(
        skill="readiness-frame-win-themes",
        keywords={"win", "theme", "themes", "discriminator", "needs", "wants", "priority"},
        accepts={"eval_handoff", "pains_handoff", "tea_leaves_handoff"},
        produces={"win_themes_handoff"},
        artifact_extensions=("json",),
        downstream_skills={"mission-readiness-framer"},
        phase_rank=13,
        role="seed priority-ranked win-theme candidates with rationale chains",
        quality_gate="Output must rank win_theme_candidates with proof_required and eval links.",
    ),
    SkillChainContract(
        skill="readiness-frame-external-research",
        keywords={"vendor", "platform", "url", "overlay", "capability", "external", "research"},
        accepts={"pains_handoff", "modernization_handoff"},
        produces={"capability_overlay_handoff"},
        artifact_extensions=("json",),
        downstream_skills={"mission-readiness-framer"},
        phase_rank=13,
        role="run independent web research for user-directed capability overlays",
        quality_gate="Output must cite web sources and map capabilities to solicitation pains with fit_to_scope.",
    ),
    SkillChainContract(
        skill="mission-readiness-framer",
        keywords={
            "readiness", "mission", "customer", "intent", "pain", "priority",
            "priorities", "theme", "themes", "win", "program", "office",
            "enabler", "workload", "implicit", "hidden", "framer", "frame",
        },
        accepts={
            "evaluation_factors",
            "requirement_graph",
            "eval_handoff",
            "workload_handoff",
            "pains_handoff",
            "modernization_handoff",
            "tea_leaves_handoff",
            "win_themes_handoff",
            "capability_overlay_handoff",
        },
        produces={"strategy_handoff", "mission_readiness_handoff", "scope_read"},
        artifact_extensions=("json", "md", "html"),
        downstream_skills={"proposal-generator"},
        phase_rank=14,
        role="compile upstream readiness handoffs into mission_readiness_frame and brief",
        quality_gate=(
            "Output must merge upstream handoffs into mission_readiness_frame, pain points, "
            "importance signals, implicit criteria, and win-theme candidates with citations."
        ),
        default_upstream_triggers={
            "proposal-generator": {"proposal", "respond", "response", "draft"},
        },
    ),
    SkillChainContract(
        skill="rfp-reverse-engineer",
        keywords={
            "reverse", "engineer", "scope", "hot", "button", "buttons",
            "hidden", "decision", "tree", "pws", "sow", "qasp", "trap",
        },
        accepts={"requirement_graph", "evaluation_factors"},
        produces={"strategy_handoff", "scope_read"},
        artifact_extensions=("json", "md", "html"),
        downstream_skills=set(),
        phase_rank=15,
        role="(deprecated) CO stance inversion and acquisition-trap forensics",
        quality_gate="Output must name scope decisions, hot buttons, discriminator hooks, and missing-section signals.",
    ),
    SkillChainContract(
        skill="workload-analyzer",
        keywords={
            "workload", "site", "sites", "staffing", "labor", "volume",
            "demand", "section", "spreadsheet", "clin", "hours", "attachment",
        },
        accepts={"workload_attachment", "obligation_data"},
        produces={"workload_handoff", "pricing_inputs"},
        artifact_extensions=("json", "xlsx", "md"),
        downstream_skills={"price-to-win", "proposal-generator"},
        phase_rank=20,
        role="turn workload data into pricing inputs",
        quality_gate="Output must summarize demand drivers, pricing assumptions, anomalies, and missing workload inputs.",
    ),
    SkillChainContract(
        skill="compliance-auditor",
        keywords={
            "compliance", "audit", "far", "dfars", "clause", "clauses",
            "shall", "l", "m", "matrix", "instruction", "evaluation",
        },
        accepts={"requirement_graph", "proposal_draft"},
        produces={"compliance_findings", "gap_list"},
        artifact_extensions=("json", "md", "xlsx", "docx"),
        downstream_skills={"proposal-generator"},
        phase_rank=30,
        role="audit instructions, clauses, and compliance gaps",
        quality_gate="Output must separate verified clauses, gaps, severity, and evidence links.",
    ),
    SkillChainContract(
        skill="oci-sweeper",
        keywords={"oci", "conflict", "impaired", "objectivity", "unequal", "access"},
        accepts={"competitor_intel", "company_history"},
        produces={"oci_findings"},
        artifact_extensions=("json", "md", "docx"),
        downstream_skills={"proposal-generator"},
        phase_rank=30,
        role="surface OCI risk and mitigation notes",
        quality_gate="Output must classify OCI risk type, evidence, severity, and mitigation option.",
    ),
    SkillChainContract(
        skill="ot-prototype-strategist",
        keywords={"ot", "prototype", "trl", "milestone", "cost", "share", "4022", "4021"},
        accepts={"scope_read", "workload_handoff"},
        produces={"ot_strategy", "prototype_cost_stack"},
        artifact_extensions=("json", "xlsx", "md"),
        downstream_skills={"proposal-generator", "renderers"},
        phase_rank=35,
        role="build OT prototype strategy and milestone cost stack",
        quality_gate="Output must define OT authority path, milestone phasing, cost-share posture, and pricing assumptions.",
        renderable=True,
    ),
    SkillChainContract(
        skill="price-to-win",
        keywords={
            "price", "pricing", "ptw", "cost", "costing", "estimate",
            "should", "wrap", "rate", "rates", "labor", "boe", "target",
        },
        accepts={"competitor_intel", "award_history", "obligation_data", "workload_handoff", "pricing_inputs"},
        produces={"pricing_stack", "ptw_workbook"},
        artifact_extensions=("json", "xlsx", "md", "docx"),
        downstream_skills={"proposal-generator", "renderers"},
        phase_rank=40,
        role="build price-to-win / should-cost estimate",
        quality_gate="Output must include low/mid/high scenarios, assumptions, missing inputs, and confidence notes.",
        renderable=True,
    ),
    SkillChainContract(
        skill="proposal-generator",
        keywords={
            "proposal", "respond", "response", "draft", "outline", "volume",
            "executive", "summary", "theme", "themes", "fab", "matrix",
        },
        accepts={"strategy_handoff", "compliance_findings", "pricing_stack", "workload_handoff", "oci_findings"},
        produces={"proposal_draft", "compliance_matrix"},
        artifact_extensions=("json", "md", "html", "docx", "xlsx"),
        downstream_skills={"renderers", "huashu-design"},
        phase_rank=50,
        role="draft proposal response artifacts from upstream evidence",
        quality_gate="Output must trace claims to evidence, address evaluation factors, and flag unsupported win themes.",
        renderable=True,
    ),
    SkillChainContract(
        skill="subcontractor-sow-builder",
        keywords={"subcontractor", "sub", "teaming", "partner", "sow", "pws"},
        accepts={"scope_read", "requirement_graph"},
        produces={"sub_sow", "sub_pws"},
        artifact_extensions=("md", "docx"),
        downstream_skills={"renderers"},
        phase_rank=50,
        role="draft downstream SOW/PWS artifact",
        quality_gate="Output must define sub scope, deliverables, standards, exclusions, and staffing handoff.",
        renderable=True,
    ),
    SkillChainContract(
        skill="renderers",
        keywords={"render", "docx", "word", "xlsx", "excel", "workbook"},
        accepts={"proposal_draft", "compliance_matrix", "pricing_stack", "ptw_workbook", "sub_sow", "ot_strategy"},
        produces={"docx", "xlsx"},
        artifact_extensions=("md", "json"),
        downstream_skills=set(),
        phase_rank=80,
        role="render structured source artifacts into Office deliverables",
        quality_gate="Output must preserve source structure and emit requested Office artifact paths.",
    ),
    SkillChainContract(
        skill="huashu-design",
        keywords={"slides", "pptx", "pdf", "html", "deck", "prototype", "visual"},
        accepts={"proposal_draft", "strategy_handoff", "pricing_stack"},
        produces={"presentation", "html", "pdf"},
        artifact_extensions=("html", "json", "md"),
        downstream_skills=set(),
        phase_rank=85,
        role="render visual/presentation deliverables",
        quality_gate="Output must produce presentation-ready visual artifact paths and name any missing visual inputs.",
    ),
]

CONTRACT_REGISTRY = SkillContractRegistry(_DEFAULT_CONTRACTS)

__all__ = ["CONTRACT_REGISTRY", "SkillChainContract", "SkillContractRegistry"]
