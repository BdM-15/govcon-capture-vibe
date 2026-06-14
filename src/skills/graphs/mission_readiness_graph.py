"""Full LangGraph DAG for mission-readiness — one node per step, each a step pipeline subgraph."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RunnableConfig

from src.skills.chain_executor import SkillChainExecutor
from src.skills.chain_models import (
    ChainRunState,
    ChainSpec,
    ChainStepRun,
    ChainStepSpec,
    utc_now_iso,
)
from src.skills.graphs.chain_events import ChainEvent, emit_chain_event
from src.skills.graphs.step_pipeline_graph import run_step_pipeline_step, use_step_pipeline


_STEP_STATUS_RANK = {
    "pending": 0,
    "running": 1,
    "partial": 2,
    "completed": 3,
    "failed": 4,
    "skipped": 5,
}


def _prefer_step_run(
    existing: ChainStepRun,
    incoming: ChainStepRun,
) -> ChainStepRun:
    """Keep furthest-along step snapshot when parallel nodes return stale chain copies."""
    left_rank = _STEP_STATUS_RANK.get(str(existing.status or ""), 0)
    right_rank = _STEP_STATUS_RANK.get(str(incoming.status or ""), 0)
    if right_rank > left_rank:
        return incoming
    if right_rank < left_rank:
        return existing
    if incoming.finished_at and not existing.finished_at:
        return incoming
    if existing.finished_at and not incoming.finished_at:
        return existing
    return incoming


def _merge_chain_state(
    left: dict[str, Any] | None,
    right: dict[str, Any],
) -> dict[str, Any]:
    """Merge parallel step node updates into one chain snapshot."""
    if not left:
        return right
    if not right:
        return left
    merged = ChainRunState.model_validate(left)
    incoming = ChainRunState.model_validate(right)
    for step_id, step_run in incoming.steps.items():
        existing = merged.steps.get(step_id)
        if existing is None:
            merged.steps[step_id] = step_run
        else:
            merged.steps[step_id] = _prefer_step_run(existing, step_run)
    if incoming.error and not merged.error:
        merged.error = incoming.error
    if incoming.updated_at and (
        not merged.updated_at or incoming.updated_at >= merged.updated_at
    ):
        merged.updated_at = incoming.updated_at

    terminal = {"completed", "partial", "failed", "skipped"}
    if all(run.status in terminal for run in merged.steps.values()):
        SkillChainExecutor._finalize_if_terminal(merged, utc_now_iso())  # noqa: SLF001
    elif incoming.status == "failed":
        merged.status = "failed"
        merged.error = incoming.error or merged.error
    return merged.model_dump()


class MissionReadinessState(TypedDict):
    chain: Annotated[dict[str, Any], _merge_chain_state]
    chain_dir: str


def build_mission_readiness_graph(spec: ChainSpec) -> StateGraph:
    """Build DAG: step nodes wired by depends_on; each step runs retrieve->finalize->retry subgraph."""
    graph = StateGraph(MissionReadinessState)
    graph.add_node("chain_finalize", _chain_finalize_node)

    dependents: dict[str, set[str]] = {step.id: set() for step in spec.steps}
    for step in spec.steps:
        for dep in step.depends_on:
            dependents.setdefault(dep, set()).add(step.id)

    for step in spec.steps:
        graph.add_node(step.id, _make_step_node(step))

    for step in spec.steps:
        if not step.depends_on:
            graph.add_edge(START, step.id)
        for dep in step.depends_on:
            graph.add_edge(dep, step.id)

    leaves = [step.id for step in spec.steps if not dependents.get(step.id)]
    for leaf in leaves:
        graph.add_edge(leaf, "chain_finalize")
    graph.add_edge("chain_finalize", END)
    return graph


def _upstream_satisfied(chain: ChainRunState, step: ChainStepSpec) -> tuple[bool, str]:
    terminal = {"completed", "partial"}
    for dep in step.depends_on:
        dep_run = chain.steps.get(dep)
        if not dep_run:
            return False, f"unknown dependency {dep}"
        if dep_run.status not in terminal:
            return False, f"upstream {dep} status={dep_run.status}"
    return True, ""


def _make_step_node(step: ChainStepSpec):
    async def _node(state: MissionReadinessState, *, config: RunnableConfig) -> dict[str, Any]:
        cfg = config.get("configurable") or {}
        runner = cfg["runner"]
        chain = ChainRunState.model_validate(state["chain"])
        chain_dir = Path(state["chain_dir"])
        step_run = chain.steps[step.id]

        if chain.status == "failed":
            if step_run.status == "pending":
                step_run.status = "skipped"
                step_run.error = chain.error or "chain failed"
                step_run.finished_at = utc_now_iso()
            return {"chain": chain.model_dump()}

        if step_run.status in {"completed", "partial", "failed", "skipped"}:
            return {"chain": chain.model_dump()}

        ok, reason = _upstream_satisfied(chain, step)
        if not ok:
            step_run.status = "skipped"
            step_run.error = reason
            step_run.finished_at = utc_now_iso()
            chain.updated_at = utc_now_iso()
            runner._run_store.write_chain_run(chain_dir, chain.model_dump())
            return {"chain": chain.model_dump()}

        input_artifacts, contract_errors = SkillChainExecutor._resolve_input_artifacts(  # noqa: SLF001
            chain,
            step,
        )
        step_run.input_artifacts = input_artifacts
        if contract_errors:
            step_run.status = "failed"
            step_run.error = "; ".join(contract_errors)
            step_run.finished_at = utc_now_iso()
            chain.status = "failed"
            chain.error = f"step {step.id} artifact contract failed: {step_run.error}"
            runner._executor._skip_pending_steps(chain, reason=chain.error)  # noqa: SLF001
            runner._run_store.write_chain_run(chain_dir, chain.model_dump())
            emit_chain_event(
                chain_dir,
                ChainEvent(
                    chain_id=chain.chain_id,
                    phase="step",
                    event="step_finished",
                    summary=step_run.error,
                    step_id=step.id,
                    skill=step.skill,
                    status="failed",
                ),
            )
            return {"chain": chain.model_dump()}

        step_run.status = "running"
        step_run.started_at = utc_now_iso()
        emit_chain_event(
            chain_dir,
            ChainEvent(
                chain_id=chain.chain_id,
                phase="step",
                event="step_started",
                summary=f"Running {step.skill}",
                step_id=step.id,
                skill=step.skill,
                status="running",
            ),
        )
        chain.updated_at = utc_now_iso()
        runner._run_store.write_chain_run(chain_dir, chain.model_dump())

        if use_step_pipeline(step):
            outcome = await run_step_pipeline_step(
                chain=chain,
                step=step,
                chain_dir=chain_dir,
                executor=runner._executor,  # noqa: SLF001
                workspace_root=Path(cfg["workspace_root"]),
                entity_payload=cfg["entity_payload"],
                llm=cfg["llm"],
                max_payload_chars=cfg.get("max_payload_chars"),
                slice_fn=cfg.get("slice_fn"),
                retrieve_fn=cfg.get("retrieve_fn"),
                runtime_mode_override=cfg.get("runtime_mode_override"),
            )
        else:
            outcome = await runner._executor._execute_step(  # noqa: SLF001
                chain,
                step=step,
                workspace=chain.workspace,
                workspace_root=Path(cfg["workspace_root"]),
                entity_payload=cfg["entity_payload"],
                llm=cfg["llm"],
                max_payload_chars=cfg.get("max_payload_chars"),
                slice_fn=cfg.get("slice_fn"),
                retrieve_fn=cfg.get("retrieve_fn"),
                runtime_mode_override=cfg.get("runtime_mode_override"),
            )

        if outcome.error:
            step_run.status = "failed"
            step_run.error = outcome.error
            chain.status = "failed"
            chain.error = f"step {step.id} failed: {step_run.error}"
            if chain.spec.stop_on_error:
                runner._executor._skip_pending_steps(chain, reason=chain.error)  # noqa: SLF001
        elif outcome.result is None:
            step_run.status = "failed"
            step_run.error = "step returned no result"
            chain.status = "failed"
            chain.error = f"step {step.id} failed: {step_run.error}"
            if chain.spec.stop_on_error:
                runner._executor._skip_pending_steps(chain, reason=chain.error)  # noqa: SLF001
        else:
            result = outcome.result
            step_run.status = "completed"
            step_run.run_id = result.run_id
            step_run.run_dir = result.run_dir
            step_run.response_preview = result.response[:2000]
            step_run.warnings = list(result.warnings or [])
            step_run.elapsed_ms = result.elapsed_ms
            if result.run_id:
                detail = runner._run_store.get_run(
                    Path(cfg["workspace_root"]),
                    step_run.skill,
                    result.run_id,
                )
                if detail:
                    step_run.artifacts = list(detail.get("artifacts") or [])
            step_run.missing_inputs = SkillChainExecutor._extract_missing_inputs(  # noqa: SLF001
                result.response
            )
            step_run.missing_outputs = SkillChainExecutor._extract_missing_outputs(  # noqa: SLF001
                step_run.artifacts
            )
            if step_run.missing_outputs:
                step_run.status = "partial"
            elif step_run.missing_inputs:
                step_run.status = "partial"

        step_run.finished_at = utc_now_iso()
        chain.updated_at = utc_now_iso()
        runner._executor._finalize_if_terminal(chain, chain.updated_at)  # noqa: SLF001
        runner._run_store.write_chain_run(chain_dir, chain.model_dump())
        emit_chain_event(
            chain_dir,
            ChainEvent(
                chain_id=chain.chain_id,
                phase="step",
                event="step_finished",
                summary=step_run.error or f"{step.skill} {step_run.status}",
                step_id=step.id,
                skill=step.skill,
                status=step_run.status,
                elapsed_ms=int(step_run.elapsed_ms or 0),
            ),
        )
        return {"chain": chain.model_dump()}

    return _node


async def _chain_finalize_node(state: MissionReadinessState, *, config: RunnableConfig) -> dict[str, Any]:
    chain = ChainRunState.model_validate(state["chain"])
    chain_dir = Path(state["chain_dir"])
    cfg = config.get("configurable") or {}
    runner = cfg["runner"]
    if not chain.finished_at:
        finished = utc_now_iso()
        SkillChainExecutor._finalize_if_terminal(chain, finished)  # noqa: SLF001
        chain.updated_at = finished
        runner._run_store.write_chain_run(chain_dir, chain.model_dump())
    emit_chain_event(
        chain_dir,
        ChainEvent(
            chain_id=chain.chain_id,
            phase="orchestration",
            event="chain_finished",
            summary=f"Chain {chain.status}",
            status=chain.status,
        ),
    )
    return {"chain": chain.model_dump()}