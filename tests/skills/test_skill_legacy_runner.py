from pathlib import Path

from src.skills.skill_legacy_runner import run_legacy_skill
from src.skills.skill_models import Skill, SkillFrontmatter


def _skill() -> Skill:
    return Skill(
        name="demo-skill",
        path="/tmp/demo-skill",
        skill_md_path="/tmp/demo-skill/SKILL.md",
        frontmatter=SkillFrontmatter(name="demo-skill", description="desc", version="1.0.0"),
        body_md="body",
    )


async def _echo(prompt: str) -> str:
    return prompt


def test_run_legacy_skill_uses_entities_block_and_persists(tmp_path: Path) -> None:
    captured = {}
    touched = []

    def persist_run(**kwargs):
        captured.update(kwargs)
        return "run-1", "run-dir"

    result = __import__("asyncio").run(
        run_legacy_skill(
            skill=_skill(),
            workspace="ws",
            user_prompt="answer",
            entity_payload={"entities": {"requirement": [], "factor": []}},
            llm=_echo,
            max_payload_chars=None,
            default_max_payload_chars=1000,
            workspace_root=tmp_path,
            persist_run=persist_run,
            touch_invocation=touched.append,
        )
    )

    assert result.entities_used == ["factor", "requirement"]
    assert result.run_id == "run-1"
    assert touched == ["demo-skill"]
    assert captured["skill_name"] == "demo-skill"
    assert captured["workspace"] == "ws"


def test_run_legacy_skill_truncates_flat_payload(tmp_path: Path) -> None:
    result = __import__("asyncio").run(
        run_legacy_skill(
            skill=_skill(),
            workspace="ws",
            user_prompt="answer",
            entity_payload={"requirement": ["x" * 100], "relationships": []},
            llm=_echo,
            max_payload_chars=20,
            default_max_payload_chars=1000,
            workspace_root=None,
            persist_run=lambda **kwargs: ("", ""),
            touch_invocation=lambda name: None,
        )
    )

    assert result.entities_used == ["requirement"]
    assert any("briefing book truncated" in warning for warning in result.warnings)


async def _stylish_echo(prompt: str) -> str:
    return "Messy — prose with ’quotes’ … and bullet ·"


def test_run_legacy_skill_normalizes_smart_punctuation(tmp_path: Path) -> None:
    captured = {}

    def persist_run(**kwargs):
        captured.update(kwargs)
        return "run-2", "run-dir"

    result = __import__("asyncio").run(
        run_legacy_skill(
            skill=_skill(),
            workspace="ws",
            user_prompt="answer",
            entity_payload={"entities": {"requirement": []}},
            llm=_stylish_echo,
            max_payload_chars=None,
            default_max_payload_chars=1000,
            workspace_root=tmp_path,
            persist_run=persist_run,
            touch_invocation=lambda name: None,
        )
    )

    assert result.response == "Messy - prose with 'quotes' ... and bullet -"
    assert captured["response"] == "Messy - prose with 'quotes' ... and bullet -"