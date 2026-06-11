"""SkillManager — discover, install, and invoke agent skills.

Skills live in ``.github/skills/<name>/SKILL.md`` (the official agentskills.io
location). Each ``SKILL.md`` is a Markdown file with YAML frontmatter:

    ---
    name: <slug>
    description: <pushy, precise trigger sentence>
    category: <design|ontology|proposal|compliance|intel|other>
    version: <semver>
    license: <spdx>
    ---

    # <Skill Title>
    <imperative instructions...>

The manager:
  * Walks ``.github/skills/`` at startup (and on demand) to register skills
  * Stores install metadata in ``var/platform/skills.json`` (a single
    workspace-independent JSON file — installed skills are global to the
    Theseus instance, not per-RFP)
  * Pulls relevant entity slices from the active workspace KG when a skill is
    invoked, then dispatches the SKILL.md instructions + entity payload to
    the configured LLM
  * Supports installation from a GitHub URL via ``git clone --depth=1`` into
    ``.github/skills/`` (no PyPI / no archive fetch — git is the contract)

Design choices:
  * No SQLite, no PyYAML, no extra deps — small inline YAML frontmatter
    parser handles only what skill files actually use (str/int/bool keys at
    top level).
  * Workspace context injection is deliberately conservative: we pull entity
    *names* and *types*, never raw chunk text, into the prompt. The skill
    can ask for chunk-level evidence via the standard query endpoints.
  * Invocation never blocks the main event loop — long LLM calls use
    ``asyncio.to_thread`` if a sync LLM client is the only option available.
"""

from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from src.skills.chain_executor import SkillChainExecutor
from src.skills.chain_models import ChainRunState, ChainSpec
from src.skills.chain_planner import ChainPlan, SkillChainPlanner
from src.skills.runs import SkillRunStore
from src.skills.run_metadata import STUDIO_EXTRA_MIME, resolve_artifact_mime
from src.skills.settings import (
    DEFAULT_SKILL_MAX_PAYLOAD_CHARS,
    resolve_skill_runtime_mode,
)
from src.skills.skill_catalog import SkillCatalog
from src.skills.skill_legacy_runner import run_legacy_skill
from src.skills.skill_models import (
    Skill,
    SkillFrontmatter,
    SkillInvocationResult,
    SkillRunSummary,
)
from src.skills.skill_tools_runner import run_tools_skill
from src.skills.tool_types import ToolError, ToolResult

logger = logging.getLogger(__name__)

# Back-compat surface for Studio download route/tests that historically imported
# mime helpers from src.skills.manager.
_STUDIO_EXTRA_MIME = STUDIO_EXTRA_MIME


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_DIR = _REPO_ROOT / ".github" / "skills"
_PLATFORM_DIR = _REPO_ROOT / "var" / "platform"
_INSTALL_LEDGER = _PLATFORM_DIR / "skills.json"


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
        _chain_depth: int = 0,
        _chain: tuple[str, ...] = (),
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
            invoke_skill_fn = self._build_invoke_skill_fn(
                workspace=workspace,
                entity_payload=entity_payload,
                llm=llm,
                max_payload_chars=max_payload_chars,
                workspace_root=workspace_root,
                slice_fn=slice_fn,
                retrieve_fn=retrieve_fn,
                runtime_mode_override=runtime_mode_override,
                chain_depth=_chain_depth,
                chain=_chain + (name,),
            )
            result = await self._tools_runner(
                skill=skill,
                workspace=workspace,
                user_prompt=user_prompt,
                workspace_root=workspace_root,
                slice_fn=slice_fn,
                retrieve_fn=retrieve_fn,
                run_store=self._run_store,
                mcp_registry=self._mcp_registry,
                touch_invocation=self._touch_invocation,
                entity_payload=entity_payload,
                invoke_skill_fn=invoke_skill_fn,
            )
            self._annotate_products(workspace_root, result)
            return result
        result = await self._legacy_runner(
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
        self._annotate_products(workspace_root, result)
        return result

    def _annotate_products(
        self,
        workspace_root: Optional[Path],
        result: SkillInvocationResult,
    ) -> None:
        if workspace_root is None or not result.run_id:
            return
        self._run_store.annotate_artifact_products(
            workspace_root,
            result.skill,
            result.run_id,
        )

    def _build_invoke_skill_fn(
        self,
        *,
        workspace: str,
        entity_payload: dict[str, Any],
        llm: Callable[[str], Awaitable[str]],
        max_payload_chars: Optional[int],
        workspace_root: Optional[Path],
        slice_fn: Optional[Callable[..., dict[str, Any]]],
        retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]],
        runtime_mode_override: Optional[str],
        chain_depth: int,
        chain: tuple[str, ...],
    ) -> Callable[..., Awaitable[ToolResult]]:
        async def _invoke_skill(
            child_name: str,
            child_prompt: str,
            context: dict[str, Any] | None = None,
        ) -> ToolResult:
            if chain_depth >= 1:
                raise ToolError("invoke_skill Tier A allows one child skill only")
            if child_name in chain:
                raise ToolError(f"invoke_skill cycle detected: {' -> '.join(chain + (child_name,))}")
            if self._catalog.get_skill(child_name) is None:
                raise ToolError(f"Unknown skill: {child_name}")
            prompt = child_prompt.strip()
            if context:
                import json as _json

                prompt += (
                    "\n\n## Parent handoff context\n"
                    "```json\n"
                    + _json.dumps(context, ensure_ascii=False, indent=2, default=str)
                    + "\n```"
                )
            result = await self.invoke(
                child_name,
                workspace=workspace,
                user_prompt=prompt,
                entity_payload=entity_payload,
                llm=llm,
                max_payload_chars=max_payload_chars,
                workspace_root=workspace_root,
                slice_fn=slice_fn,
                retrieve_fn=retrieve_fn,
                runtime_mode_override=runtime_mode_override,
                _chain_depth=chain_depth + 1,
                _chain=chain,
            )
            artifacts: list[dict[str, Any]] = []
            if workspace_root is not None and result.run_id:
                detail = self._run_store.get_run(workspace_root, child_name, result.run_id)
                if detail:
                    artifacts = list(detail.get("artifacts") or [])
            return ToolResult(
                payload={
                    "skill": result.skill,
                    "run_id": result.run_id,
                    "run_dir": result.run_dir,
                    "finish_reason": result.finish_reason,
                    "elapsed_ms": result.elapsed_ms,
                    "warnings": result.warnings,
                    "response_preview": result.response[:2000],
                    "artifacts": artifacts,
                },
                transcript_extra={
                    "child_skill": result.skill,
                    "child_run_id": result.run_id,
                    "artifact_count": len(artifacts),
                },
            )

        return _invoke_skill

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


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class SkillManager:
    """Discover and invoke agent skills.

    The manager is a singleton (see :func:`get_skill_manager`) and is safe to
    call concurrently — discovery and ledger writes are guarded by a lock.
    """

    def __init__(
        self,
        skills_dir: Path = _SKILLS_DIR,
        ledger_path: Path = _INSTALL_LEDGER,
        mcps_root: Optional[Path] = None,
    ) -> None:
        self.skills_dir = skills_dir
        self.ledger_path = ledger_path
        self._catalog = SkillCatalog(skills_dir=skills_dir, ledger_path=ledger_path)
        self._run_store = SkillRunStore()
        # Phase 4a: MCP client subsystem. Lazy-imported so legacy-mode
        # deployments without any MCPs installed pay zero cost.
        from src.skills.mcp_client import MCPRegistry

        if mcps_root is None:
            mcps_root = _REPO_ROOT / "tools" / "mcps"
        self._mcp_registry = MCPRegistry.from_root(mcps_root)
        self._executor = SkillExecutor(
            catalog=self._catalog,
            run_store=self._run_store,
            mcp_registry=self._mcp_registry,
        )

    # ---- Discovery ----------------------------------------------------

    def discover(self) -> dict[str, Skill]:
        return self._catalog.discover()

    # ---- Public read API ---------------------------------------------

    def list_skills(self, include_developer: bool = False) -> list[dict[str, Any]]:
        return self._catalog.list_skills(include_developer=include_developer)

    def get_skill(self, name: str) -> Optional[Skill]:
        return self._catalog.get_skill(name)

    def get_skill_detail(self, name: str) -> Optional[dict[str, Any]]:
        return self._catalog.get_skill_detail(name)

    def plan_chain(
        self,
        *,
        prompt: str,
        outcome: str = "",
        max_steps: int = 8,
        include_rendering: bool = True,
    ) -> ChainPlan:
        """Plan a logical skill chain from installed skill contracts."""
        planner = SkillChainPlanner(self.list_skills(include_developer=False))
        return planner.plan(
            prompt=prompt,
            outcome=outcome,
            max_steps=max_steps,
            include_rendering=include_rendering,
        )

    # ---- Install / uninstall -----------------------------------------

    async def install_from_github(self, url: str, name: Optional[str] = None) -> Skill:
        return await self._catalog.install_from_github(url, name=name)

    async def uninstall(self, name: str) -> bool:
        return await self._catalog.uninstall(name)

    # ---- Invocation ---------------------------------------------------

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
        _chain_depth: int = 0,
        _chain: tuple[str, ...] = (),
    ) -> SkillInvocationResult:
        """Run a skill against an injected workspace context.

        Args:
            name: Skill slug.
            workspace: Active workspace name (for telemetry / output envelope).
            user_prompt: Free-text user instruction (may be empty for
                "use defaults" mode).
            entity_payload: Briefing book dict produced by the route layer
                (Phase 1.5 contract). Expected top-level keys:
                ``entities`` (``{entity_type: [{name, description,
                source_chunks}]}``), ``source_chunks`` (verbatim RFP text
                blocks the model is required to quote from), and
                ``relationships`` (typed KG edges between sliced entities).
                Falls back gracefully if older callers pass a flat
                ``{entity_type: [...]}`` dict.
            llm: Async callable that takes a single composed prompt string
                and returns the model's response. Lets the caller decide which
                model / temperature to use.
            max_payload_chars: Hard cap on the JSON-serialized entity payload
                included in the prompt (truncated with a marker if exceeded).
            slice_fn: Optional Phase 1.5 KG slice callable (route layer's
                ``_slice_workspace_entities``). Required for tools-mode skills
                that call ``kg_entities``.
            retrieve_fn: Optional Phase 1.6 retrieval callable (route layer's
                ``_retrieve_relevant_entities_for_skill``). Required for
                tools-mode skills that call ``kg_chunks``.
            runtime_mode_override: Force ``"tools"`` or ``"legacy"`` regardless
                of what the skill's ``metadata.runtime`` declares. Used by the
                env var ``SKILL_RUNTIME_MODE`` and tests.
        """
        return await self._executor.invoke(
            name,
            workspace=workspace,
            user_prompt=user_prompt,
            entity_payload=entity_payload,
            llm=llm,
            max_payload_chars=max_payload_chars,
            workspace_root=workspace_root,
            slice_fn=slice_fn,
            retrieve_fn=retrieve_fn,
            runtime_mode_override=runtime_mode_override,
            _chain_depth=_chain_depth,
            _chain=_chain,
        )

    async def invoke_chain(
        self,
        spec: ChainSpec,
        *,
        workspace: str,
        entity_payload: dict[str, Any],
        llm: Callable[[str], Awaitable[str]],
        max_payload_chars: Optional[int] = None,
        workspace_root: Optional[Path] = None,
        slice_fn: Optional[Callable[..., dict[str, Any]]] = None,
        retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]] = None,
        runtime_mode_override: Optional[str] = None,
        source_chain_id: str = "",
        mode: str = "original",
    ) -> ChainRunState:
        """Run a deterministic multi-skill chain through SkillChainExecutor."""
        if workspace_root is None:
            workspace_root = _REPO_ROOT / "rag_storage" / workspace
        executor = SkillChainExecutor(
            invoke_skill=self.invoke,
            run_store=self._run_store,
        )
        return await executor.invoke(
            spec,
            workspace=workspace,
            workspace_root=workspace_root,
            llm=llm,
            entity_payload=entity_payload,
            max_payload_chars=max_payload_chars,
            slice_fn=slice_fn,
            retrieve_fn=retrieve_fn,
            runtime_mode_override=runtime_mode_override,
            source_chain_id=source_chain_id,
            mode=mode,
        )

    async def resume_chain(
        self,
        chain: ChainRunState,
        *,
        workspace_root: Path,
        entity_payload: dict[str, Any],
        llm: Callable[[str], Awaitable[str]],
        max_payload_chars: Optional[int] = None,
        slice_fn: Optional[Callable[..., dict[str, Any]]] = None,
        retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]] = None,
        runtime_mode_override: Optional[str] = None,
        from_step_id: str = "",
        resume_notes: str = "",
    ) -> ChainRunState:
        """Resume an existing chain, preserving completed steps by default."""
        executor = SkillChainExecutor(
            invoke_skill=self.invoke,
            run_store=self._run_store,
        )
        return await executor.resume(
            chain,
            workspace_root=workspace_root,
            llm=llm,
            entity_payload=entity_payload,
            max_payload_chars=max_payload_chars,
            slice_fn=slice_fn,
            retrieve_fn=retrieve_fn,
            runtime_mode_override=runtime_mode_override,
            from_step_id=from_step_id,
            resume_notes=resume_notes,
        )

    def list_chain_runs(
        self, workspace_root: Path, limit: int = 50
    ) -> list[dict[str, Any]]:
        return self._run_store.list_chain_runs(workspace_root, limit=limit)

    def get_chain_run(
        self, workspace_root: Path, chain_id: str
    ) -> Optional[dict[str, Any]]:
        return self._run_store.get_chain_run(workspace_root, chain_id)

    def project_chain_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_store.project_chain_payload(payload)

    def list_runs(
        self, workspace_root: Path, skill_name: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        return self._run_store.list_runs(
            workspace_root,
            skill_name=skill_name,
            limit=limit,
        )

    def get_run(
        self, workspace_root: Path, skill_name: str, run_id: str
    ) -> Optional[dict[str, Any]]:
        return self._run_store.get_run(workspace_root, skill_name, run_id)

    def project_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_store.project_run_payload(payload)

    def delete_run(
        self, workspace_root: Path, skill_name: str, run_id: str
    ) -> bool:
        return self._run_store.delete_run(workspace_root, skill_name, run_id)

    def purge_run(
        self, workspace_root: Path, skill_name: str, run_id: str
    ) -> bool:
        return self._run_store.purge_run(workspace_root, skill_name, run_id)

    def purge_trashed_runs(
        self,
        workspace_root: Path,
        *,
        skill_name: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._run_store.purge_trashed_runs(
            workspace_root, skill_name=skill_name
        )

    def trash_run(
        self,
        workspace_root: Path,
        skill_name: str,
        run_id: str,
    ) -> Optional[dict[str, Any]]:
        return self._run_store.trash_run(workspace_root, skill_name, run_id)

    def list_trashed_runs(
        self,
        workspace_root: Path,
        skill_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._run_store.list_trashed_runs(
            workspace_root,
            skill_name=skill_name,
            limit=limit,
        )

    def restore_trashed_runs(
        self,
        workspace_root: Path,
        trash_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        return self._run_store.restore_trashed_runs(workspace_root, trash_ids)

    def list_deliverables(
        self, workspace_root: Path, limit: int = 500
    ) -> list[dict[str, Any]]:
        return self._run_store.list_deliverables(workspace_root, limit=limit)

    def get_artifact_path(
        self,
        workspace_root: Path,
        skill_name: str,
        run_id: str,
        filename: str,
    ) -> Optional[Path]:
        return self._run_store.get_artifact_path(
            workspace_root,
            skill_name,
            run_id,
            filename,
        )

    def delete_artifacts(
        self,
        workspace_root: Path,
        artifacts: list[dict[str, str]],
    ) -> dict[str, list[dict[str, str]]]:
        return self._run_store.delete_artifacts(workspace_root, artifacts)

    def trash_artifacts(
        self,
        workspace_root: Path,
        artifacts: list[dict[str, str]],
    ) -> dict[str, list[dict[str, Any]]]:
        return self._run_store.trash_artifacts(workspace_root, artifacts)

    def list_trashed_artifacts(
        self,
        workspace_root: Path,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return self._run_store.list_trashed_artifacts(workspace_root, limit=limit)

    def purge_trashed_artifacts(
        self,
        workspace_root: Path,
    ) -> dict[str, int]:
        return self._run_store.purge_trashed_artifacts(workspace_root)

    def restore_trashed_artifacts(
        self,
        workspace_root: Path,
        trash_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        return self._run_store.restore_trashed_artifacts(workspace_root, trash_ids)

# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_SINGLETON: Optional[SkillManager] = None


def get_skill_manager() -> SkillManager:
    """Return the process-wide SkillManager, discovering on first use."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = SkillManager()
        _SINGLETON.discover()
    return _SINGLETON
