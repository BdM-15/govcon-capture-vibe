from src.skills.skill_models import Skill, SkillFrontmatter, parse_frontmatter


def test_parse_frontmatter_handles_metadata_and_allowed_tools() -> None:
    text = """---
name: demo-skill
description: test trigger
allowed-tools:
  - Read
  - Write
metadata:
  runtime: tools
  mcps:
    - usaspending
    - sam_gov
  category: intel
  version: 1.2.3
  personas_secondary: [capture-manager, proposal-manager]
---

# Body
Do work.
"""

    frontmatter, body = parse_frontmatter(text)

    assert frontmatter.name == "demo-skill"
    assert frontmatter.runtime_mode == "tools"
    assert frontmatter.required_mcps == ["usaspending", "sam_gov"]
    assert frontmatter.category == "intel"
    assert frontmatter.version == "1.2.3"
    assert frontmatter.allowed_tools == ["Read", "Write"]
    assert frontmatter.metadata["personas_secondary"] == ["capture-manager", "proposal-manager"]
    assert body == "# Body\nDo work."


def test_skill_to_summary_uses_taxonomy_defaults() -> None:
    skill = Skill(
        name="demo-skill",
        path="/tmp/demo-skill",
        skill_md_path="/tmp/demo-skill/SKILL.md",
        frontmatter=SkillFrontmatter(name="demo-skill", description="desc"),
        body_md="# Demo",
    )

    summary = skill.to_summary()

    assert summary["personas_primary"] == "none"
    assert summary["personas_secondary"] == []
    assert summary["shipley_phases"] == []
    assert summary["runtime_mode"] == "legacy"