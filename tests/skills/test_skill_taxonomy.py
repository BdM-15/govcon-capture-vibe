"""Phase 4j contract tests for the cross-skill taxonomy.

Enforces the closed vocabularies defined in docs/SKILL_TAXONOMY.md across
EVERY skill under .github/skills/. Drift here breaks the UI grouping +
filter pills, so this test is a hard gate.

Closed vocabularies
-------------------
- personas_primary: 8 IDs from the extraction prompt + sentinel "none"
- personas_secondary: subset of the same 8 IDs (no "none")
- shipley_phases: subset of 6 lifecycle phases
- capability: one of 7 capability verbs
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv

load_dotenv()


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_ROOT = _REPO_ROOT / ".github" / "skills"


# Closed vocabularies — MUST mirror docs/SKILL_TAXONOMY.md.
# When the extraction prompt's USER PERSONAS YOU SUPPORT block changes,
# update these sets AND audit every SKILL.md (per Cross-Cutting Checklist
# item 8 in .github/copilot-instructions.md).
_ALLOWED_PERSONAS = {
    "capture_manager",
    "proposal_manager",
    "proposal_writer",
    "cost_estimator",
    "contracts_manager",
    "technical_sme",
    "legal_compliance",
    "program_manager",
}
_PERSONA_PRIMARY_VALUES = _ALLOWED_PERSONAS | {"none"}
_ALLOWED_PHASES = {
    "pursuit",
    "capture",
    "strategy",
    "proposal_development",
    "negotiation",
    "post_award",
}
_ALLOWED_CAPABILITIES = {
    "research",
    "analyze",
    "draft",
    "audit",
    "estimate",
    "render",
    "meta",
}
_ALLOWED_SKILL_ROLES = {
    "standalone",
    "slice",
    "orchestrator",
}


def _discover_skill_dirs() -> list[Path]:
    return sorted(
        d
        for d in _SKILLS_ROOT.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


def _load_frontmatter(skill_dir: Path) -> dict:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---"), f"{skill_dir.name}: missing YAML frontmatter"
    _, fm_text, _ = text.split("---", 2)
    fm = yaml.safe_load(fm_text)
    assert isinstance(fm, dict), f"{skill_dir.name}: frontmatter is not a mapping"
    return fm


@pytest.fixture(scope="module")
def all_skills() -> list[tuple[str, dict]]:
    dirs = _discover_skill_dirs()
    assert dirs, "no skills discovered under .github/skills/"
    return [(d.name, _load_frontmatter(d)) for d in dirs]


def test_every_skill_has_metadata_block(all_skills) -> None:
    for name, fm in all_skills:
        assert "metadata" in fm, (
            f"{name}: SKILL.md frontmatter is missing the `metadata:` block. "
            f"Phase 4j requires personas_primary / personas_secondary / "
            f"shipley_phases / capability under metadata."
        )
        assert isinstance(fm["metadata"], dict), (
            f"{name}: metadata is not a mapping"
        )


def test_every_skill_has_personas_primary(all_skills) -> None:
    for name, fm in all_skills:
        meta = fm.get("metadata", {}) or {}
        val = meta.get("personas_primary")
        assert val is not None, (
            f"{name}: metadata.personas_primary is missing. Use one of "
            f"{sorted(_PERSONA_PRIMARY_VALUES)}."
        )
        assert val in _PERSONA_PRIMARY_VALUES, (
            f"{name}: metadata.personas_primary={val!r} is not in the closed "
            f"vocabulary {sorted(_PERSONA_PRIMARY_VALUES)}"
        )


def test_every_skill_has_valid_personas_secondary(all_skills) -> None:
    for name, fm in all_skills:
        meta = fm.get("metadata", {}) or {}
        val = meta.get("personas_secondary", [])
        assert isinstance(val, list), (
            f"{name}: metadata.personas_secondary must be a list (got {type(val).__name__})"
        )
        invalid = set(val) - _ALLOWED_PERSONAS
        assert not invalid, (
            f"{name}: metadata.personas_secondary has invalid IDs {sorted(invalid)}. "
            f"Allowed: {sorted(_ALLOWED_PERSONAS)} (note: 'none' is NOT valid for secondary)"
        )
        # personas_primary should not appear in secondary (avoid duplication).
        primary = meta.get("personas_primary")
        if primary and primary != "none":
            assert primary not in val, (
                f"{name}: personas_primary={primary!r} duplicated in personas_secondary"
            )


def test_every_skill_has_valid_shipley_phases(all_skills) -> None:
    for name, fm in all_skills:
        meta = fm.get("metadata", {}) or {}
        val = meta.get("shipley_phases", [])
        assert isinstance(val, list), (
            f"{name}: metadata.shipley_phases must be a list (got {type(val).__name__})"
        )
        invalid = set(val) - _ALLOWED_PHASES
        assert not invalid, (
            f"{name}: metadata.shipley_phases has invalid values {sorted(invalid)}. "
            f"Allowed: {sorted(_ALLOWED_PHASES)}"
        )


def test_every_skill_has_valid_skill_role_when_declared(all_skills) -> None:
    for name, fm in all_skills:
        meta = fm.get("metadata", {}) or {}
        val = meta.get("skill_role")
        if val is None:
            continue
        assert val in _ALLOWED_SKILL_ROLES, (
            f"{name}: metadata.skill_role={val!r} is not in {_ALLOWED_SKILL_ROLES}"
        )


def test_every_skill_has_valid_capability(all_skills) -> None:
    for name, fm in all_skills:
        meta = fm.get("metadata", {}) or {}
        val = meta.get("capability", "")
        assert val, (
            f"{name}: metadata.capability is missing. Use one of "
            f"{sorted(_ALLOWED_CAPABILITIES)}."
        )
        assert val in _ALLOWED_CAPABILITIES, (
            f"{name}: metadata.capability={val!r} is not in the closed "
            f"vocabulary {sorted(_ALLOWED_CAPABILITIES)}"
        )


def test_persona_primary_aligns_with_extraction_prompt() -> None:
    """The V8 extraction prompt Part A is the source of truth for the persona vocabulary.

    V8-4 (issue #124): govcon_lightrag_json.txt was retired. The prompt is now built
    in-module by _build_v8_system_prompt(). When the persona list in Part A changes,
    this test will fail until docs/SKILL_TAXONOMY.md and SKILL.md frontmatter are
    re-audited.
    """
    from prompts.govcon_prompt import _build_v8_system_prompt
    prompt = _build_v8_system_prompt()
    expected = {
        "Capture Managers",
        "Proposal Managers",
        "Proposal Writers",
        "Cost Estimators",
        "Contracts Managers",
        "Technical SMEs",
        "Legal/Compliance",
        "Program Managers",
    }
    missing = [label for label in expected if label not in prompt]
    assert not missing, (
        f"Extraction prompt no longer mentions personas {missing}. If the "
        f"persona vocabulary was intentionally changed, update "
        f"docs/SKILL_TAXONOMY.md AND _ALLOWED_PERSONAS in this test AND "
        f"audit every SKILL.md per Cross-Cutting Checklist item 8."
    )


def test_taxonomy_doc_exists() -> None:
    doc = _REPO_ROOT / "docs" / "SKILL_TAXONOMY.md"
    assert doc.exists(), (
        "docs/SKILL_TAXONOMY.md is the authoritative reference for the "
        "Phase 4j taxonomy. Restore it before merging."
    )
    text = doc.read_text(encoding="utf-8")
    for token in (
        "personas_primary",
        "personas_secondary",
        "shipley_phases",
        "capability",
    ):
        assert token in text, f"docs/SKILL_TAXONOMY.md missing reference to `{token}`"
