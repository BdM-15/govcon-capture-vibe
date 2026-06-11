"""Phase 4h contract tests for the rfp-reverse-engineer skill.

Mirrors test_price_to_win_skill.py pattern. This skill declares NO MCPs
(reads workspace KG only). Body invariants are reverse-engineering specific:
JSON envelope structure, trap detector fields, decision-tree reconstruction.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from dotenv import load_dotenv

load_dotenv()

from src.skills.manager import SkillManager


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_ROOT = _REPO_ROOT / ".github" / "skills"
_SKILL_DIR = _SKILLS_ROOT / "rfp-reverse-engineer"
_SKILL_MD = _SKILL_DIR / "SKILL.md"
_EVALS = _SKILL_DIR / "evals" / "evals.json"
_REFERENCES_DIR = _SKILL_DIR / "references"

_ALLOWED_FRONTMATTER_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}

_REQUIRED_REFERENCES = [
    "reverse_engineering_catalog.md",
    "discriminator_hooks.md",
    "rfp_signal_patterns.md",
    "far_citations.md",
]


def _read_frontmatter_and_body(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise AssertionError(f"{path} missing YAML frontmatter")
    _, fm_text, body = text.split("---", 2)
    return yaml.safe_load(fm_text), body


def test_rfp_reverse_engineer_frontmatter_is_spec_compliant() -> None:
    fm, _ = _read_frontmatter_and_body(_SKILL_MD)
    extra = set(fm) - _ALLOWED_FRONTMATTER_FIELDS
    assert not extra, (
        f"rfp-reverse-engineer SKILL.md has non-spec top-level frontmatter "
        f"fields: {extra}. Move them under `metadata:`."
    )
    assert fm["name"] == "rfp-reverse-engineer"
    assert fm["metadata"]["status"] == "deprecated"
    assert fm["metadata"]["superseded_by"] == "mission-readiness-framer"
    assert len(fm["description"]) <= 1024, (
        f"description is {len(fm['description'])} chars (spec max 1024)"
    )
    assert "USE WHEN" in fm["description"]
    assert "DO NOT USE FOR" in fm["description"]


def test_rfp_reverse_engineer_declares_no_mcps() -> None:
    mgr = SkillManager(_SKILLS_ROOT)
    skill = mgr.get_skill("rfp-reverse-engineer")
    assert skill is not None
    assert skill.frontmatter.runtime_mode == "tools"
    assert not skill.frontmatter.required_mcps, (
        f"rfp-reverse-engineer must NOT declare MCPs; got "
        f"{skill.frontmatter.required_mcps}"
    )


def test_rfp_reverse_engineer_body_has_envelope_and_trap_markers() -> None:
    _, body = _read_frontmatter_and_body(_SKILL_MD)
    for marker in (
        "decision_tree_reconstruction",
        "hot_buttons",
        "discriminator_hooks",
        "ghost_language",
        "missing_sections",
        "cpff_form_signal",
        "key_personnel_clause_check",
        "qasp_cpars_check",
        "rfp_reverse_engineering.json",
        "FAR 52.237-2",
        "(d)(1) or (d)(2)",
        "CPARS",
    ):
        assert marker in body, (
            f"SKILL.md body missing required marker '{marker}' — reverse-"
            f"engineering envelope or trap detector has regressed"
        )


def test_rfp_reverse_engineer_catalog_enumerates_6_blocks() -> None:
    catalog = (_REFERENCES_DIR / "reverse_engineering_catalog.md").read_text(encoding="utf-8")
    for block in (
        "Block 1: Mission",
        "Block 2: Technical Scope",
        "Block 3: Scale",
        "Block 4: Organizational",
        "Block 5: Contract Structure",
        "Block 6: Quality",
    ):
        assert block in catalog, (
            f"reverse_engineering_catalog.md missing '{block}'"
        )


def test_rfp_reverse_engineer_references_exist() -> None:
    for ref in _REQUIRED_REFERENCES:
        path = _REFERENCES_DIR / ref
        assert path.exists(), (
            f"missing required reference: {path.relative_to(_REPO_ROOT)}"
        )
        text = path.read_text(encoding="utf-8")
        assert len(text) > 500, f"{ref} suspiciously short ({len(text)} chars)"


def test_rfp_reverse_engineer_body_references_no_fake_mcps() -> None:
    _, body = _read_frontmatter_and_body(_SKILL_MD)
    assert "mcp__" not in body, (
        "rfp-reverse-engineer body references mcp__<server>__<tool> but "
        "declares no MCPs — fix one or the other"
    )


def test_rfp_reverse_engineer_evals_exercise_key_branches() -> None:
    data = json.loads(_EVALS.read_text(encoding="utf-8"))
    evals = data["evals"]
    assert len(evals) >= 3, f"expected at least 3 evals, got {len(evals)}"

    all_text = json.dumps(evals).lower()
    # Decision-tree reconstruction, trap detection, ghost language must each
    # be exercised by at least one eval.
    for branch_marker in ("decision", "trap", "ghost"):
        assert branch_marker in all_text, (
            f"evals do not exercise the '{branch_marker}' branch"
        )

    for e in evals:
        assert e.get("expected_signals"), f"eval {e.get('id')} missing expected_signals"
        assert e.get("anti_signals"), f"eval {e.get('id')} missing anti_signals"


def test_rfp_reverse_engineer_upstream_md_present() -> None:
    upstream = _SKILL_DIR / "UPSTREAM.md"
    assert upstream.exists(), "UPSTREAM.md missing — required for vendored skills"
    text = upstream.read_text(encoding="utf-8")
    assert "MIT" in text and "1102tools" in text, "UPSTREAM.md must cite MIT + 1102tools origin"
    assert "Stance-Inversion Contract" in text, "UPSTREAM.md must document the stance-inversion contract"
