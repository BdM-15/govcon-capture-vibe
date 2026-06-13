"""Tests for skill family / role grouping and API enrichment."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.skills.chain_contracts import CONTRACT_REGISTRY
from src.skills.skill_catalog import SkillCatalog
from src.skills.skill_grouping import (
    enrich_skill_summary,
    resolve_skill_family,
    resolve_skill_role,
)
from src.skills.skill_models import Skill, parse_frontmatter


def _load_skill(name: str) -> Skill:
    skill_dir = Path(__file__).resolve().parents[2] / ".github" / "skills" / name
    frontmatter, body = parse_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
    return Skill(
        name=name,
        path=str(skill_dir),
        skill_md_path=str(skill_dir / "SKILL.md"),
        frontmatter=frontmatter,
        body_md=body,
    )


def test_readiness_slice_resolves_family_and_role() -> None:
    skill = _load_skill("readiness-frame-eval")
    assert resolve_skill_family(skill) == "readiness-frame"
    assert resolve_skill_role(skill) == "slice"


def test_mission_readiness_framer_is_orchestrator() -> None:
    skill = _load_skill("mission-readiness-framer")
    assert resolve_skill_role(skill) == "orchestrator"
    assert resolve_skill_family(skill) == "readiness-frame"


def test_enrich_skill_summary_includes_chain_metadata() -> None:
    skill = _load_skill("mission-readiness-framer")
    summary = enrich_skill_summary(skill)
    assert summary["skill_role"] == "orchestrator"
    assert summary["skill_family"] == "readiness-frame"
    assert summary["chain"]["registered"] is True
    assert "eval_handoff" in summary["chain"]["accepts"]
    assert summary["orchestrator_compiles"]


def test_catalog_list_skills_returns_grouping_fields() -> None:
    catalog = SkillCatalog(
        skills_dir=Path(__file__).resolve().parents[2] / ".github" / "skills",
        ledger_path=Path(__file__).resolve().parents[2] / "var" / "platform" / "skills.json",
    )
    catalog.discover()
    mrf = next(item for item in catalog.list_skills() if item["name"] == "mission-readiness-framer")
    assert mrf["skill_role"] == "orchestrator"
    slices = [
        item
        for item in catalog.list_skills()
        if str(item.get("skill_family")) == "readiness-frame"
        and item.get("skill_role") == "slice"
    ]
    assert len(slices) >= 7


def test_readiness_frame_skills_have_taxonomy_frontmatter() -> None:
    skills_root = Path(__file__).resolve().parents[2] / ".github" / "skills"
    for skill_dir in sorted(skills_root.glob("readiness-frame-*")):
        fm = yaml.safe_load((skill_dir / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1])
        meta = fm.get("metadata") or {}
        assert meta.get("personas_primary")
        assert meta.get("capability")
        assert meta.get("skill_role") == "slice"
        assert meta.get("skill_family") == "readiness-frame"


def test_proposal_generator_orchestrator_in_registry() -> None:
    contract = CONTRACT_REGISTRY.require("proposal-generator")
    assert len(contract.accepts) >= 3