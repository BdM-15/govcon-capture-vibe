"""LangGraph-backed execution for Theseus skill chains."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from src.skills.chain_models import (
    ChainRunState,
    ChainSpec,
    ChainStepRun,
    ChainStepSpec,
    utc_now_iso,
)
from src.skills.skill_models import SkillInvocationResult


class ChainExecutionState(TypedDict, total=False):
    chain: dict[str, Any]
    blocked: bool


InvokeSkillCallable = Callable[..., Awaitable[SkillInvocationResult]]


class SkillChainExecutor:
    """Execute a validated chain spec with existing skill invocation primitives."""

    def __init__(
        self,
        *,
        invoke_skill: InvokeSkillCallable,
        run_store: Any,
    ) -> None:
        self._invoke_skill = invoke_skill
        self._run_store = run_store

    async def invoke(
        self,
        spec: ChainSpec,
        *,
        workspace: str,
        workspace_root: Path,
        llm: Callable[[str], Awaitable[str]],
        entity_payload: dict[str, Any] | None = None,
        max_payload_chars: Optional[int] = None,
        slice_fn: Optional[Callable[..., dict[str, Any]]] = None,
        retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]] = None,
        runtime_mode_override: Optional[str] = None,
    ) -> ChainRunState:
        chain_id, chain_dir = self._run_store.create_chain_run(
            workspace_root=workspace_root,
            name=spec.name,
            prompt=spec.prompt,
        )
        initial = ChainRunState(
            chain_id=chain_id,
            workspace=workspace,
            status="running",
            spec=spec,
            steps={
                step.id: ChainStepRun(id=step.id, skill=step.skill)
                for step in spec.steps
            },
        )
        self._run_store.write_chain_run(chain_dir, initial.model_dump())

        graph = self._build_graph(
            spec=spec,
            chain_dir=chain_dir,
            workspace=workspace,
            workspace_root=workspace_root,
            llm=llm,
            entity_payload=entity_payload or {},
            max_payload_chars=max_payload_chars,
            slice_fn=slice_fn,
            retrieve_fn=retrieve_fn,
            runtime_mode_override=runtime_mode_override,
        )
        final_state = await graph.ainvoke(
            {"chain": initial.model_dump(), "blocked": False}
        )
        return ChainRunState.model_validate(final_state["chain"])

    def _build_graph(
        self,
        *,
        spec: ChainSpec,
        chain_dir: Path,
        workspace: str,
        workspace_root: Path,
        llm: Callable[[str], Awaitable[str]],
        entity_payload: dict[str, Any],
        max_payload_chars: Optional[int],
        slice_fn: Optional[Callable[..., dict[str, Any]]],
        retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]],
        runtime_mode_override: Optional[str],
    ):
        builder: StateGraph[ChainExecutionState] = StateGraph(ChainExecutionState)

        previous_node = START
        for step in spec.steps:
            node_name = step.id
            builder.add_node(
                node_name,
                self._step_node(
                    step,
                    chain_dir=chain_dir,
                    workspace=workspace,
                    workspace_root=workspace_root,
                    llm=llm,
                    entity_payload=entity_payload,
                    max_payload_chars=max_payload_chars,
                    slice_fn=slice_fn,
                    retrieve_fn=retrieve_fn,
                    runtime_mode_override=runtime_mode_override,
                ),
            )
            builder.add_edge(previous_node, node_name)
            previous_node = node_name
        builder.add_edge(previous_node, END)
        return builder.compile()

    def _step_node(
        self,
        step: ChainStepSpec,
        *,
        chain_dir: Path,
        workspace: str,
        workspace_root: Path,
        llm: Callable[[str], Awaitable[str]],
        entity_payload: dict[str, Any],
        max_payload_chars: Optional[int],
        slice_fn: Optional[Callable[..., dict[str, Any]]],
        retrieve_fn: Optional[Callable[..., Awaitable[dict[str, Any]]]],
        runtime_mode_override: Optional[str],
    ):
        async def _run(state: ChainExecutionState) -> ChainExecutionState:
            chain = ChainRunState.model_validate(state["chain"])
            if state.get("blocked"):
                chain.steps[step.id].status = "skipped"
                chain.steps[step.id].error = "chain blocked by earlier failure"
                chain.updated_at = utc_now_iso()
                self._finalize_if_terminal(chain, chain.updated_at)
                self._run_store.write_chain_run(chain_dir, chain.model_dump())
                return {"chain": chain.model_dump(), "blocked": True}

            missing = [dep for dep in step.depends_on if chain.steps[dep].status != "completed"]
            if missing:
                chain.steps[step.id].status = "skipped"
                chain.steps[step.id].error = "dependency not completed: " + ", ".join(missing)
                chain.status = "failed"
                chain.error = chain.steps[step.id].error
                chain.updated_at = utc_now_iso()
                self._finalize_if_terminal(chain, chain.updated_at)
                self._run_store.write_chain_run(chain_dir, chain.model_dump())
                return {"chain": chain.model_dump(), "blocked": chain.spec.stop_on_error}

            step_run = chain.steps[step.id]
            step_run.status = "running"
            step_run.started_at = utc_now_iso()
            chain.updated_at = step_run.started_at
            self._run_store.write_chain_run(chain_dir, chain.model_dump())

            try:
                result = await self._invoke_skill(
                    step.skill,
                    workspace=workspace,
                    user_prompt=self._compose_step_prompt(chain, step),
                    entity_payload=entity_payload,
                    llm=llm,
                    max_payload_chars=max_payload_chars,
                    workspace_root=workspace_root,
                    slice_fn=slice_fn,
                    retrieve_fn=retrieve_fn,
                    runtime_mode_override=runtime_mode_override,
                    _chain_depth=1,
                    _chain=(step.skill,),
                )
            except Exception as exc:  # noqa: BLE001
                step_run.status = "failed"
                step_run.error = str(exc)
                step_run.finished_at = utc_now_iso()
                chain.status = "failed"
                chain.error = f"step {step.id} failed: {exc}"
                chain.updated_at = step_run.finished_at
                self._finalize_if_terminal(chain, step_run.finished_at)
                self._run_store.write_chain_run(chain_dir, chain.model_dump())
                return {"chain": chain.model_dump(), "blocked": chain.spec.stop_on_error}

            step_run.status = "completed"
            step_run.run_id = result.run_id
            step_run.run_dir = result.run_dir
            step_run.response_preview = result.response[:2000]
            step_run.warnings = list(result.warnings or [])
            step_run.elapsed_ms = result.elapsed_ms
            step_run.finished_at = utc_now_iso()
            if result.run_id:
                detail = self._run_store.get_run(workspace_root, step.skill, result.run_id)
                if detail:
                    step_run.artifacts = list(detail.get("artifacts") or [])
            chain.updated_at = step_run.finished_at
            self._finalize_if_terminal(chain, step_run.finished_at)
            self._run_store.write_chain_run(chain_dir, chain.model_dump())
            return {"chain": chain.model_dump(), "blocked": False}

        return _run

    @staticmethod
    def _finalize_if_terminal(chain: ChainRunState, finished_at: str) -> None:
        terminal = {"completed", "failed", "skipped"}
        if not all(run.status in terminal for run in chain.steps.values()):
            return
        failed = any(run.status == "failed" for run in chain.steps.values())
        blocked = any(run.status == "skipped" and run.error for run in chain.steps.values())
        chain.status = "failed" if failed or blocked else "completed"
        chain.finished_at = finished_at

    @staticmethod
    def _compose_step_prompt(chain: ChainRunState, step: ChainStepSpec) -> str:
        upstream = {
            step_id: run.model_dump()
            for step_id, run in chain.steps.items()
            if run.status == "completed"
        }
        handoff = {
            "chain_id": chain.chain_id,
            "chain_name": chain.spec.name,
            "chain_prompt": chain.spec.prompt,
            "step_id": step.id,
            "step_context": step.context,
            "input_artifacts": [artifact.model_dump() for artifact in step.input_artifacts],
            "upstream_steps": upstream,
        }
        return (
            (step.prompt or chain.spec.prompt or "Run this chain step.").strip()
            + "\n\n## Theseus Chain Handoff\n"
            + "```json\n"
            + json.dumps(handoff, ensure_ascii=False, indent=2, default=str)
            + "\n```"
        )


__all__ = ["SkillChainExecutor"]