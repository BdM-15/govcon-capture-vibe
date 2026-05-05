import asyncio
from pathlib import Path

from src.skills.manager import SkillExecutor
from src.skills.runs import SkillRunStore
from src.skills.skill_catalog import SkillCatalog
from src.skills.skill_models import Skill, SkillFrontmatter, SkillInvocationResult


def _skill(tmp_path: Path, *, runtime: str) -> Skill:
    skill_dir = tmp_path / runtime
    skill_dir.mkdir()
    return Skill(
        name=f"demo-{runtime}",
        path=str(skill_dir),
        skill_md_path=str(skill_dir / "SKILL.md"),
        frontmatter=SkillFrontmatter(
            name=f"demo-{runtime}",
            description="desc",
            metadata={"runtime": runtime},
        ),
        body_md="body",
    )


class FakeCatalog:
    def __init__(self, skill: Skill | None):
        self.skill = skill
        self.touched: list[str] = []

    def get_skill(self, name: str):
        if self.skill and self.skill.name == name:
            return self.skill
        return None

    def touch_invocation(self, name: str) -> None:
        self.touched.append(name)


def _result(name: str) -> SkillInvocationResult:
    return SkillInvocationResult(
        skill=name,
        workspace="ws",
        response="ok",
        entities_used=[],
        warnings=[],
        elapsed_ms=1,
        prompt_tokens_estimate=1,
        run_id="run-1",
        run_dir="run-dir",
    )


def test_skill_executor_uses_tools_runner_for_tools_mode(tmp_path: Path) -> None:
    skill = _skill(tmp_path, runtime="tools")
    catalog = FakeCatalog(skill)
    captured = {}

    async def fake_tools_runner(**kwargs):
        captured.update(kwargs)
        kwargs["touch_invocation"](kwargs["skill"].name)
        return _result(kwargs["skill"].name)

    executor = SkillExecutor(
        catalog=catalog,  # type: ignore[arg-type]
        run_store=SkillRunStore(),
        mcp_registry=object(),
        tools_runner=fake_tools_runner,
    )

    result = asyncio.run(
        executor.invoke(
            skill.name,
            workspace="ws",
            user_prompt="answer",
            entity_payload={},
            llm=lambda prompt: None,
            workspace_root=tmp_path,
        )
    )

    assert result.skill == skill.name
    assert captured["skill"].name == skill.name
    assert captured["workspace"] == "ws"
    assert catalog.touched == [skill.name]


def test_skill_executor_uses_legacy_runner_for_legacy_mode(tmp_path: Path) -> None:
    skill = _skill(tmp_path, runtime="legacy")
    catalog = FakeCatalog(skill)
    captured = {}

    async def fake_legacy_runner(**kwargs):
        captured.update(kwargs)
        kwargs["touch_invocation"](kwargs["skill"].name)
        return _result(kwargs["skill"].name)

    async def fake_llm(prompt: str) -> str:
        return prompt

    executor = SkillExecutor(
        catalog=catalog,  # type: ignore[arg-type]
        run_store=SkillRunStore(),
        mcp_registry=object(),
        legacy_runner=fake_legacy_runner,
    )

    result = asyncio.run(
        executor.invoke(
            skill.name,
            workspace="ws",
            user_prompt="answer",
            entity_payload={"entities": {}},
            llm=fake_llm,
            workspace_root=tmp_path,
            max_payload_chars=123,
        )
    )

    assert result.skill == skill.name
    assert captured["skill"].name == skill.name
    assert captured["max_payload_chars"] == 123
    assert callable(captured["persist_run"])
    assert catalog.touched == [skill.name]


def test_skill_executor_raises_for_unknown_skill(tmp_path: Path) -> None:
    executor = SkillExecutor(
        catalog=FakeCatalog(None),  # type: ignore[arg-type]
        run_store=SkillRunStore(),
        mcp_registry=object(),
    )

    try:
        asyncio.run(
            executor.invoke(
                "missing",
                workspace="ws",
                user_prompt="answer",
                entity_payload={},
                llm=lambda prompt: None,
                workspace_root=tmp_path,
            )
        )
    except KeyError as exc:
        assert "Unknown skill" in str(exc)
    else:
        raise AssertionError("expected KeyError for missing skill")