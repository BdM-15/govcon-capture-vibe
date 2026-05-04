"""Skill execution lifecycle for discovered skills."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from src.skills.runs import SkillRunStore
from src.skills.settings import (
    DEFAULT_SKILL_MAX_PAYLOAD_CHARS,
    resolve_skill_runtime_mode,
)
from src.skills.skill_catalog import SkillCatalog
from src.skills.skill_legacy_runner import run_legacy_skill
from src.skills.skill_models import SkillInvocationResult
from src.skills.skill_tools_runner import run_tools_skill


class SkillExecutor:
    """Run discovered skills through legacy or tools mode."""

    def __init__(
        self,
        *,
        catalog: SkillCatalog,
        run_store: SkillRunStore,
        mcp_registry: Any,
        default_max_payload_chars: int = DEFAULT_SKILL_MAX_PAYLOAD_CHARS,
        resolve_runtime_mode_fn: Callable[..., str] = resolve_skill_runtime_mode,
        legacy_runner: Callable[..., Awaitable[SkillInvocationResult]] = run_legacy_skill,
        tools_runner: Callable[..., Awaitable[SkillInvocationResult]] = run_tools_skill,
    ) -> None:
        self._catalog = catalog
        self._run_store = run_store
        self._mcp_registry = mcp_registry
        self._default_max_payload_chars = default_max_payload_chars
        self._resolve_runtime_mode = resolve_runtime_mode_fn
        self._legacy_runner = legacy_runner
        self._tools_runner = tools_runner

    async def invoke(
        self,
        name: str,
        *,
        workspace: str,
        user_prompt: str,
        entity_payload: dict[str, Any],
        llm: Callable[[str], Awaitable[str]],
        max_payload_chars: Optional[int] = None,
        workspace_root: Optional[Path] = None,
        slice_fn: Optional[Callable[..., dict[str, Any]]] = None,
        retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]] = None,
        runtime_mode_override: Optional[str] = None,
    ) -> SkillInvocationResult:
        """Run one discovered skill through its configured runtime mode."""
        skill = self._catalog.get_skill(name)
        if skill is None:
            raise KeyError(f"Unknown skill: {name}")

        mode = self._resolve_runtime_mode(
            skill.frontmatter.runtime_mode,
            runtime_mode_override=runtime_mode_override,
        )
        if mode == "tools":
            return await self._tools_runner(
                skill=skill,
                workspace=workspace,
                user_prompt=user_prompt,
                workspace_root=workspace_root,
                slice_fn=slice_fn,
                retrieve_fn=retrieve_fn,
                run_store=self._run_store,
                mcp_registry=self._mcp_registry,
                touch_invocation=self._touch_invocation,
            )
        return await self._legacy_runner(
            skill=skill,
            workspace=workspace,
            user_prompt=user_prompt,
            entity_payload=entity_payload,
            llm=llm,
            max_payload_chars=max_payload_chars,
            default_max_payload_chars=self._default_max_payload_chars,
            workspace_root=workspace_root,
            persist_run=self._persist_legacy_run,
            touch_invocation=self._touch_invocation,
        )

    def _persist_legacy_run(
        self,
        *,
        workspace_root: Path,
        skill_name: str,
        workspace: str,
        user_prompt: str,
        composed_prompt: str,
        response: str,
        entities_used: list[str],
        warnings: list[str],
        elapsed_ms: int,
        started_at: datetime,
    ) -> tuple[str, str]:
        return self._run_store.persist_legacy_run(
            workspace_root=workspace_root,
            skill_name=skill_name,
            workspace=workspace,
            user_prompt=user_prompt,
            composed_prompt=composed_prompt,
            response=response,
            entities_used=entities_used,
            warnings=warnings,
            elapsed_ms=elapsed_ms,
            started_at=started_at,
        )

    def _touch_invocation(self, name: str) -> None:
        self._catalog.touch_invocation(name)