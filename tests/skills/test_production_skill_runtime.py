"""Contract tests: production govcon skills run in tools mode.

Issue #187 migrates the last production-relevant legacy skills to
``metadata.runtime: tools`` so they use the multi-turn tool loop (KG lazy
fetch, run_script, artifacts) instead of the single-shot legacy runner.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.skills.manager import SkillExecutor, SkillManager
from src.skills.runs import SkillRunStore
from src.skills.skill_models import SkillInvocationResult


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_ROOT = _REPO_ROOT / ".github" / "skills"

# Active production skills that participate in capture/proposal workflows.
# Meta/dev skills (tdd, grill-me, etc.) may remain legacy until migrated.
PRODUCTION_TOOLS_SKILLS = (
    "workload-analyzer",
    "data-analyzer",
    "huashu-design",
)


@pytest.mark.parametrize("skill_name", PRODUCTION_TOOLS_SKILLS)
def test_production_skills_are_cataloged_as_tools_mode(skill_name: str) -> None:
    mgr = SkillManager(_SKILLS_ROOT)
    skill = mgr.get_skill(skill_name)
    assert skill is not None
    assert skill.frontmatter.runtime_mode == "tools"


def _invocation_result(skill_name: str) -> SkillInvocationResult:
    return SkillInvocationResult(
        skill=skill_name,
        workspace="ws",
        response="ok",
        entities_used=[],
        warnings=[],
        elapsed_ms=1,
        prompt_tokens_estimate=1,
        run_id="run-1",
        run_dir="run-dir",
    )


@pytest.mark.parametrize("skill_name", PRODUCTION_TOOLS_SKILLS)
def test_skill_executor_routes_production_skills_through_tools_runner(
    skill_name: str,
    tmp_path: Path,
) -> None:
    mgr = SkillManager(_SKILLS_ROOT)
    catalog = mgr._catalog  # noqa: SLF001 — exercise real discovery in integration test
    routed_via: list[str] = []

    async def fake_tools_runner(**kwargs):
        routed_via.append("tools")
        kwargs["touch_invocation"](kwargs["skill"].name)
        return _invocation_result(kwargs["skill"].name)

    async def fake_legacy_runner(**kwargs):
        routed_via.append("legacy")
        return _invocation_result(kwargs["skill"].name)

    executor = SkillExecutor(
        catalog=catalog,
        run_store=SkillRunStore(),
        mcp_registry=object(),
        tools_runner=fake_tools_runner,
        legacy_runner=fake_legacy_runner,
    )

    result = asyncio.run(
        executor.invoke(
            skill_name,
            workspace="ws",
            user_prompt="analyze workload",
            entity_payload={},
            llm=lambda prompt: asyncio.sleep(0, result=prompt),
            workspace_root=tmp_path,
        )
    )

    assert result.skill == skill_name
    assert routed_via == ["tools"]