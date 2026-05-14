"""Contract tests for the theseus-ui-reviewer skill.

Layered like other skill contract tests (e.g. test_competitive_intel_skill.py):

1. Spec-compliance of SKILL.md frontmatter + body invariants.
2. References + evals exist and are well-formed.
3. The skill discovers, invokes through SkillManager, and the eval harness
   over evals.json detects the planted token violation in eval #1 (this is
   the "audit accuracy" regression gate — if doctrine is removed from the
   SKILL.md / references, the heuristic check below fails).
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import yaml

from src.skills.manager import SkillManager


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_ROOT = _REPO_ROOT / ".github" / "skills"
_SKILL_DIR = _SKILLS_ROOT / "theseus-ui-reviewer"
_SKILL_MD = _SKILL_DIR / "SKILL.md"

_ALLOWED_FRONTMATTER_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}


def _read_frontmatter_and_body(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{path} missing YAML frontmatter"
    _, fm_text, body = text.split("---", 2)
    return yaml.safe_load(fm_text), body


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Layer 1 — spec compliance
# ---------------------------------------------------------------------------


def test_frontmatter_is_spec_compliant() -> None:
    fm, _ = _read_frontmatter_and_body(_SKILL_MD)
    extra = set(fm) - _ALLOWED_FRONTMATTER_FIELDS
    assert not extra, (
        f"theseus-ui-reviewer SKILL.md has non-spec top-level frontmatter: {extra}. "
        f"Move under metadata."
    )
    assert fm["name"] == "theseus-ui-reviewer"
    assert len(fm["description"]) <= 1024, (
        f"description is {len(fm['description'])} chars (spec max 1024)"
    )
    assert "USE WHEN" in fm["description"]
    assert "DO NOT USE FOR" in fm["description"]


def test_body_under_500_lines() -> None:
    _, body = _read_frontmatter_and_body(_SKILL_MD)
    n = len(body.splitlines())
    assert n <= 500, f"SKILL.md body is {n} lines (spec cap 500)"


def test_workflow_is_numbered_checklist() -> None:
    _, body = _read_frontmatter_and_body(_SKILL_MD)
    assert "## Workflow Checklist" in body
    assert re.search(r"^\s*1\. ", body, re.MULTILINE), "workflow must be numbered"


def test_no_scripts_no_templates_no_chain_contract() -> None:
    assert not (_SKILL_DIR / "scripts").exists(), "no scripts/ folder allowed (#150)"
    assert not (_SKILL_DIR / "templates").exists(), "use assets/ not templates/"
    contracts = (_REPO_ROOT / "src" / "skills" / "chain_contracts.py").read_text(
        encoding="utf-8"
    )
    assert "theseus-ui-reviewer" not in contracts, (
        "no chain contract allowed for theseus-ui-reviewer per #150"
    )


# ---------------------------------------------------------------------------
# Layer 2 — references + evals
# ---------------------------------------------------------------------------


def test_required_references_exist() -> None:
    for fname in ("style-tokens.md", "component-patterns.md", "anti-patterns.md"):
        p = _SKILL_DIR / "references" / fname
        assert p.exists(), f"required reference missing: {p}"
        assert p.stat().st_size > 200, f"{fname} is suspiciously small"


def test_references_one_level_deep() -> None:
    refs = _SKILL_DIR / "references"
    for child in refs.iterdir():
        assert child.is_file(), (
            f"references/{child.name} is a directory; references must be one level deep"
        )


def test_evals_json_well_formed() -> None:
    evals_path = _SKILL_DIR / "evals" / "evals.json"
    assert evals_path.exists()
    data = json.loads(evals_path.read_text(encoding="utf-8"))
    assert data["skill_name"] == "theseus-ui-reviewer"
    assert isinstance(data["evals"], list)
    assert len(data["evals"]) >= 3, "spec requires >= 3 eval prompts"
    for ev in data["evals"]:
        assert "id" in ev and "prompt" in ev
        assert isinstance(ev.get("expectations"), list) and ev["expectations"], (
            f"eval {ev.get('id')} missing non-empty expectations"
        )


def test_first_eval_targets_planted_hex_violation() -> None:
    """Acceptance criterion: at least one eval names a planted token violation
    in a fixture component (e.g. fixture with #00ffff flagged as raw hex)."""
    data = json.loads((_SKILL_DIR / "evals" / "evals.json").read_text(encoding="utf-8"))
    matched = [
        ev
        for ev in data["evals"]
        if "#00ffff" in ev["prompt"]
        and any("raw-hex" in exp for exp in ev["expectations"])
    ]
    assert matched, (
        "expected at least one eval prompt with planted '#00ffff' "
        "and a 'raw-hex' expectation"
    )


# ---------------------------------------------------------------------------
# Layer 3 — discovery + invocation + audit-accuracy gate
# ---------------------------------------------------------------------------


def test_skill_manager_discovers_skill() -> None:
    mgr = SkillManager(_SKILLS_ROOT)
    skills = mgr.discover()
    assert "theseus-ui-reviewer" in skills


def test_skill_manager_invoke_returns_envelope() -> None:
    """Smoke-test: invoke the skill with a fake LLM and verify the runtime
    composes a prompt + returns a non-empty envelope on the response field."""
    mgr = SkillManager(_SKILLS_ROOT)

    captured: dict[str, str] = {}

    async def fake_llm(prompt: str, system_prompt: str = "") -> str:
        captured["prompt"] = prompt
        return json.dumps(
            {
                "skill": "theseus-ui-reviewer",
                "summary": "1 critical",
                "top_three": ["bg-[#00ffff]"],
                "findings": [
                    {
                        "severity": "critical",
                        "category": "token",
                        "rule": "raw-hex-vs-token",
                        "excerpt": "bg-[#00ffff]",
                        "fix": "use `bg-neon-cyan` (var(--neon-cyan))",
                    }
                ],
            }
        )

    result = _run(
        mgr.invoke(
            "theseus-ui-reviewer",
            workspace="_test",
            user_prompt='Audit: <button class="bg-[#00ffff]">x</button>',
            entity_payload={"entities": {}, "source_chunks": [], "relationships": []},
            llm=fake_llm,
        )
    )

    assert result.skill == "theseus-ui-reviewer"
    assert result.response, "skill returned empty response"
    envelope = json.loads(result.response)
    assert envelope["skill"] == "theseus-ui-reviewer"
    assert envelope["findings"], "envelope has zero findings"
    # The prompt the runtime composed must include the SKILL.md doctrine
    # so the model knows what to flag — this is the audit-accuracy gate.
    assert "raw-hex-vs-token" in captured["prompt"], (
        "composed prompt is missing the raw-hex doctrine — "
        "regression in SKILL.md or anti-patterns.md"
    )
    assert "var(--neon-cyan)" in captured["prompt"], (
        "composed prompt is missing the neon-cyan token reference — "
        "regression in references/style-tokens.md"
    )


def test_planted_violation_doctrine_present_in_skill() -> None:
    """The SKILL.md + references must explicitly teach the model to flag
    raw hex like #00ffff in favor of var(--neon-cyan). This is the
    audit-accuracy gate from #150 acceptance criteria — if doctrine drifts,
    this fails and the eval harness can no longer detect the planted
    violation."""
    skill_text = _SKILL_MD.read_text(encoding="utf-8")
    anti = (_SKILL_DIR / "references" / "anti-patterns.md").read_text(encoding="utf-8")
    tokens = (_SKILL_DIR / "references" / "style-tokens.md").read_text(encoding="utf-8")

    assert "raw-hex-vs-token" in anti, "raw-hex-vs-token rule missing"
    assert "var(--neon-cyan)" in tokens, "neon-cyan token doc missing"
    # SKILL.md must reference the token doctrine so the model loads the rule.
    assert "raw hex" in skill_text.lower() or "raw-hex" in skill_text.lower()
