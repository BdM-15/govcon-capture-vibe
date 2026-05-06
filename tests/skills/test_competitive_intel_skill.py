"""Phase 4d contract tests for the competitive-intel skill.

Two layers (mirrors test_usaspending_manifest.py):

1. **Always-on**: spec-compliance of SKILL.md frontmatter + body invariants
   (mcps allowlist, tools-mode runtime, body references real MCP tools).

2. **Opt-in (live)**: spawn the upstream usaspending MCP server, list its
   advertised tools, and confirm every ``mcp__usaspending__<tool>`` name
   referenced in SKILL.md actually exists. Catches upstream drift.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import pytest
import yaml

from src.skills.manager import SkillManager
from src.skills.mcp_client import MCPRegistry


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_ROOT = _REPO_ROOT / ".github" / "skills"
_SKILL_DIR = _SKILLS_ROOT / "competitive-intel"
_SKILL_MD = _SKILL_DIR / "SKILL.md"
_MCPS_ROOT = _REPO_ROOT / "tools" / "mcps"


# Open Skills spec: only these six top-level frontmatter fields are allowed.
_ALLOWED_FRONTMATTER_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _read_frontmatter_and_body(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise AssertionError(f"{path} missing YAML frontmatter")
    _, fm_text, body = text.split("---", 2)
    return yaml.safe_load(fm_text), body


# ---------------------------------------------------------------------------
# Layer 1 — offline spec + body invariants (always runs)
# ---------------------------------------------------------------------------


def test_competitive_intel_frontmatter_is_spec_compliant() -> None:
    fm, _ = _read_frontmatter_and_body(_SKILL_MD)
    extra = set(fm) - _ALLOWED_FRONTMATTER_FIELDS
    assert not extra, (
        f"competitive-intel SKILL.md has non-spec top-level frontmatter fields: {extra}. "
        f"Move them under `metadata:`."
    )
    assert fm["name"] == "competitive-intel"
    # Spec: description max 1024 chars
    assert len(fm["description"]) <= 1024, (
        f"description is {len(fm['description'])} chars (spec max 1024)"
    )
    assert "USE WHEN" in fm["description"], "description should be 'pushy' (include USE WHEN)"
    assert "DO NOT USE FOR" in fm["description"], "description should fence off neighbour skills"


def test_competitive_intel_declares_usaspending_mcp() -> None:
    mgr = SkillManager(_SKILLS_ROOT)
    skill = mgr.get_skill("competitive-intel")
    assert skill is not None
    assert skill.frontmatter.runtime_mode == "tools"
    assert skill.frontmatter.required_mcps == ["usaspending"]


def test_competitive_intel_body_references_real_mcp_tools_only() -> None:
    """Every `mcp__usaspending__<tool>` mentioned in the body must be in the
    allowlist of tools the upstream advertises in its current vendored version.

    Offline check — we hard-code the curated subset the workflow actually uses.
    The live test below (THESEUS_LIVE_MCP=1) cross-checks against the live
    server in case upstream renames or drops a tool.
    """
    _, body = _read_frontmatter_and_body(_SKILL_MD)
    referenced = set(re.findall(r"mcp__usaspending__([a-z_]+)", body))
    assert referenced, "SKILL.md body references zero usaspending MCP tools — nothing to test"

    # Curated whitelist for v0.3.2 (verified live via test_usaspending_manifest.py).
    # Keep in sync with references/data_sources.md tool reference table.
    known_v032 = {
        "search_awards",
        "lookup_piid",
        "get_award_detail",
        "get_transactions",
        "get_idv_children",
        "get_idv_activity",
        "spending_by_category",
        "autocomplete_naics",
        "autocomplete_psc",
        "get_psc_filter_tree",
        "list_toptier_agencies",
        "autocomplete_recipient",
        "get_recipient_profile",
        "get_recipient_children",
    }
    unknown = referenced - known_v032
    assert not unknown, (
        f"SKILL.md references usaspending tools not in the v0.3.2 whitelist: {unknown}. "
        f"If upstream added them, update this test + references/data_sources.md."
    )


def test_competitive_intel_workflow_b_uses_deterministic_collector() -> None:
    _, body = _read_frontmatter_and_body(_SKILL_MD)

    assert "collect_competitive_obligation_intel" in body
    assert "writes `artifacts/competitive_intel_obligation.json` directly" in body


def test_competitive_intel_declares_workflow_c_and_parent_summary_rules() -> None:
    _, body = _read_frontmatter_and_body(_SKILL_MD)

    assert "Workflow C (Single Award / Order Burn Intel)" in body
    assert "keep the cover note parent-level and insight-driven" in body
    assert "Use `award_rollups` / `obligations.by_award` as the canonical grouped structure" in body
    assert "If `parent_vehicle_awardees` is present" in body
    assert "The number you state in prose must equal `parent_vehicle_awardee_count`" in body
    assert 'scope="vehicle"' in body
    assert 'scope="single_award"' in body
    assert "Do not call `read_file` on `artifacts/competitive_intel_obligation.json`" in body


# ---------------------------------------------------------------------------
# Layer 2 — live drift check (opt-in)
# ---------------------------------------------------------------------------


_LIVE = os.environ.get("THESEUS_LIVE_MCP") == "1"


@pytest.mark.skipif(
    not _LIVE,
    reason="set THESEUS_LIVE_MCP=1 to spawn uvx and verify SKILL.md tool refs against live MCP",
)
def test_skill_body_tool_refs_match_live_mcp() -> None:
    """Run live: confirm every mcp__usaspending__<tool> in SKILL.md is
    actually advertised by the running upstream server. Catches drift the
    moment an upstream version bump renames a tool.
    """
    _, body = _read_frontmatter_and_body(_SKILL_MD)
    referenced = set(re.findall(r"mcp__usaspending__([a-z_]+)", body))

    async def _go():
        registry = MCPRegistry.from_root(_MCPS_ROOT)
        startup = await registry.start_run_sessions(
            run_id="phase4d-skill-contract", requested=["usaspending"]
        )
        try:
            session = startup.sessions["usaspending"]
            advertised = {t.name for t in session.tools}
            missing = referenced - advertised
            assert not missing, (
                f"SKILL.md references {missing} but upstream usaspending MCP only "
                f"advertises {sorted(advertised)[:5]}… ({len(advertised)} tools total)"
            )
        finally:
            await registry.shutdown_run("phase4d-skill-contract")
            await registry.shutdown_all()

    _run(_go())
