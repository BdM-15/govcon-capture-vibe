from src.skills.skill_models import Skill, SkillFrontmatter
from src.skills.skill_prompting import compose_skill_prompt


def test_compose_skill_prompt_includes_core_contract() -> None:
    skill = Skill(
        name="demo-skill",
        path="/tmp/demo-skill",
        skill_md_path="/tmp/demo-skill/SKILL.md",
        frontmatter=SkillFrontmatter(name="demo-skill", description="desc", version="1.2.3"),
        body_md="# Steps\nDo the thing.",
    )

    prompt = compose_skill_prompt(skill, "workspace-a", "Need answer", '{"entities": {}}')

    assert "# Agent Skill: demo-skill (1.2.3)" in prompt
    assert "## Workspace Briefing Book (JSON)" in prompt
    assert "### Citation Discipline (MANDATORY)" in prompt
    assert "Need answer" in prompt
    assert '{"entities": {}}' in prompt


def test_compose_skill_prompt_uses_defaults_when_user_prompt_blank() -> None:
    skill = Skill(
        name="demo-skill",
        path="/tmp/demo-skill",
        skill_md_path="/tmp/demo-skill/SKILL.md",
        frontmatter=SkillFrontmatter(name="demo-skill", description="desc"),
        body_md="body",
    )

    prompt = compose_skill_prompt(skill, "workspace-a", "   ", "{}")

    assert "(use skill defaults)" in prompt