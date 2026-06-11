"""Contract tests for the mission-readiness-framer skill."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from src.skills.manager import SkillManager

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_ROOT = _REPO_ROOT / ".github" / "skills"
_SKILL_DIR = _SKILLS_ROOT / "mission-readiness-framer"
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
    "output_contract.md",
    "readiness_signal_catalog.md",
    "customer_intent_signals.md",
    "narrative_template.md",
]


def _read_frontmatter_and_body(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise AssertionError(f"{path} missing YAML frontmatter")
    _, fm_text, body = text.split("---", 2)
    return yaml.safe_load(fm_text), body


def test_mission_readiness_framer_frontmatter_is_spec_compliant() -> None:
    fm, _ = _read_frontmatter_and_body(_SKILL_MD)
    extra = set(fm) - _ALLOWED_FRONTMATTER_FIELDS
    assert not extra, (
        f"mission-readiness-framer SKILL.md has non-spec top-level frontmatter "
        f"fields: {extra}. Move them under `metadata:`."
    )
    assert fm["name"] == "mission-readiness-framer"
    assert len(fm["description"]) <= 1024, (
        f"description is {len(fm['description'])} chars (spec max 1024)"
    )
    assert "USE WHEN" in fm["description"]
    assert "DO NOT USE FOR" in fm["description"]
    assert fm["metadata"]["status"] == "active"


def test_mission_readiness_framer_declares_no_mcps() -> None:
    mgr = SkillManager(_SKILLS_ROOT)
    skill = mgr.get_skill("mission-readiness-framer")
    assert skill is not None
    assert skill.frontmatter.runtime_mode == "tools"
    assert not skill.frontmatter.required_mcps, (
        f"mission-readiness-framer must NOT declare MCPs; got "
        f"{skill.frontmatter.required_mcps}"
    )


def test_mission_readiness_framer_body_has_envelope_markers() -> None:
    _, body = _read_frontmatter_and_body(_SKILL_MD)
    for marker in (
        "mission_readiness_frame",
        "customer_pain_points",
        "importance_signals",
        "implicit_criteria",
        "win_theme_candidates",
        "mission_readiness_frame.json",
        "program office",
        "readiness",
        "workload_enablers",
    ):
        assert marker in body, (
            f"SKILL.md body missing required marker '{marker}'"
        )


def test_mission_readiness_framer_references_exist() -> None:
    for ref in _REQUIRED_REFERENCES:
        path = _REFERENCES_DIR / ref
        assert path.exists(), (
            f"missing required reference: {path.relative_to(_REPO_ROOT)}"
        )
        text = path.read_text(encoding="utf-8")
        assert len(text) > 200, f"{ref} suspiciously short ({len(text)} chars)"


def test_mission_readiness_framer_body_references_no_fake_mcps() -> None:
    _, body = _read_frontmatter_and_body(_SKILL_MD)
    assert "mcp__" not in body, (
        "mission-readiness-framer body references mcp__<server>__<tool> but "
        "declares no MCPs — fix one or the other"
    )


def test_mission_readiness_framer_evals_exercise_key_branches() -> None:
    data = json.loads(_EVALS.read_text(encoding="utf-8"))
    evals = data["evals"]
    assert len(evals) >= 3, f"expected at least 3 evals, got {len(evals)}"

    all_text = json.dumps(evals).lower()
    for branch_marker in ("readiness", "cross-walk", "proxy"):
        assert branch_marker in all_text, (
            f"evals do not exercise the '{branch_marker}' branch"
        )

    for entry in evals:
        assert entry.get("expected_signals"), f"eval {entry.get('id')} missing expected_signals"
        assert entry.get("anti_signals"), f"eval {entry.get('id')} missing anti_signals"


def test_mission_readiness_framer_upstream_md_present() -> None:
    upstream = _SKILL_DIR / "UPSTREAM.md"
    assert upstream.exists(), "UPSTREAM.md missing"
    text = upstream.read_text(encoding="utf-8")
    assert "mission-readiness-framer" in text
    assert "rfp-reverse-engineer" in text