"""LangGraph wave orchestration for Theseus skill chains."""

from __future__ import annotations

import asyncio
import json
import operator
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RunnableConfig
from src.skills.chain_dag import all_steps_terminal, compute_execution_waves, ready_step_ids
from src.skills.chain_executor import SkillChainExecutor
from src.skills.chain_models import (
    ChainRunState,
    ChainSpec,
    ChainStepRun,
    ChainStepSpec,
    utc_now_iso,
)
from src.skills.graphs.chain_events import ChainEvent, emit_chain_event, read_chain_events
from src.skills.chain_step_gates import apply_step_quality_gate
from src.skills.graphs.mission_readiness_graph import (
    MissionReadinessState,
    build_mission_readiness_graph,
)
from src.skills.graphs.step_pipeline_graph import run_step_pipeline_step, use_step_pipeline

InvokeSkillCallable = Callable[..., Awaitable[Any]]


class ChainGraphState(TypedDict):
    chain: dict[str, Any]
    chain_dir: str
    wave_index: int
    events: list[dict[str, Any]]


def use_langgraph_for_spec(spec: ChainSpec) -> bool:
    preset = str((spec.context or {}).get("preset") or "").strip().lower()
    return preset == "mission-readiness"


class LangGraphChainRunner:
    """Execute ChainSpec via LangGraph wave nodes with structured event stream."""

    def __init__(
        self,
        *,
        invoke_skill: InvokeSkillCallable,
        run_store: Any,
    ) -> None:
        self._executor = SkillChainExecutor(invoke_skill=invoke_skill, run_store=run_store)
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
        source_chain_id: str = "",
        mode: str = "original",
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
            mode=mode,
            source_chain_id=source_chain_id,
            spec=spec,
            steps={
                step.id: ChainStepRun(id=step.id, skill=step.skill) for step in spec.steps
            },
        )
        self._executor._write_execution_plan(chain_dir, spec)  # noqa: SLF001
        self._run_store.write_chain_run(chain_dir, initial.model_dump())

        emit_chain_event(
            chain_dir,
            ChainEvent(
                chain_id=chain_id,
                phase="orchestration",
                event="chain_started",
                summary=f"LangGraph chain started ({len(spec.steps)} steps)",
                status="running",
            ),
        )

        mission_readiness = use_langgraph_for_spec(spec)
        if mission_readiness:
            graph = build_mission_readiness_graph(spec)
            initial_state: dict[str, Any] = {
                "chain": initial.model_dump(),
                "chain_dir": str(chain_dir),
            }
        else:
            graph = self._build_wave_graph()
            initial_state = {
                "chain": initial.model_dump(),
                "chain_dir": str(chain_dir),
                "wave_index": 0,
                "events": [],
            }

        checkpointer = MemorySaver()
        compiled = graph.compile(checkpointer=checkpointer)

        run_config: dict[str, Any] = {
            "configurable": {
                "thread_id": chain_id,
                "workspace": workspace,
                "workspace_root": str(workspace_root),
                "llm": llm,
                "max_payload_chars": max_payload_chars,
                "slice_fn": slice_fn,
                "retrieve_fn": retrieve_fn,
                "runtime_mode_override": runtime_mode_override,
                "entity_payload": entity_payload or {},
                "runner": self,
            }
        }
        if not mission_readiness:
            run_config["configurable"]["waves"] = compute_execution_waves(spec)

        result = await compiled.ainvoke(initial_state, config=run_config)
        return ChainRunState.model_validate(result["chain"])

    @staticmethod
    def _build_wave_graph():
        graph = StateGraph(ChainGraphState)
        graph.add_node("run_wave", _run_wave_node)
        graph.add_node("finalize", _finalize_node)
        graph.add_edge(START, "run_wave")
        graph.add_conditional_edges(
            "run_wave",
            _route_after_wave,
            {"run_wave": "run_wave", "finalize": "finalize"},
        )
        graph.add_edge("finalize", END)
        return graph


def _route_after_wave(state: ChainGraphState) -> str:
    chain = ChainRunState.model_validate(state["chain"])
    if chain.status in {"failed"} or all_steps_terminal(chain.steps):
        return "finalize"
    return "run_wave"


async def _run_wave_node(state: ChainGraphState, *, config: RunnableConfig) -> dict[str, Any]:
    cfg = config.get("configurable") or {}
    runner: LangGraphChainRunner = cfg["runner"]
    chain = ChainRunState.model_validate(state["chain"])
    chain_dir = Path(state["chain_dir"])
    waves: list[list[str]] = cfg["waves"]

    if chain.status == "failed" or all_steps_terminal(chain.steps):
        return {"chain": chain.model_dump(), "events": []}

    ready_ids = ready_step_ids(chain.spec, chain.steps)
    if not ready_ids:
        chain.status = "failed"
        chain.error = "chain deadlock: no ready steps"
        chain.updated_at = utc_now_iso()
        runner._run_store.write_chain_run(chain_dir, chain.model_dump())
        emit_chain_event(
            chain_dir,
            ChainEvent(
                chain_id=chain.chain_id,
                phase="orchestration",
                event="chain_deadlock",
                summary=chain.error,
                status="failed",
            ),
        )
        return {"chain": chain.model_dump(), "events": []}

    wave_label = next(
        (index for index, wave in enumerate(waves) if set(wave) & set(ready_ids)),
        state["wave_index"],
    )
    emit_chain_event(
        chain_dir,
        ChainEvent(
            chain_id=chain.chain_id,
            phase="wave",
            event="wave_started",
            summary=f"Wave {wave_label + 1}: {', '.join(ready_ids)}",
            status="running",
            detail={"step_ids": ready_ids},
        ),
    )

    ready_steps = [step for step in chain.spec.steps if step.id in ready_ids]
    blocked = False
    for step in ready_steps:
        step_run = chain.steps[step.id]
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
            blocked = True
            break
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

    if blocked:
        runner._executor._skip_pending_steps(chain, reason=chain.error)  # noqa: SLF001
        runner._executor._finalize_if_terminal(chain, utc_now_iso())  # noqa: SLF001
        runner._run_store.write_chain_run(chain_dir, chain.model_dump())
        return {"chain": chain.model_dump(), "wave_index": state["wave_index"] + 1, "events": []}

    chain.updated_at = utc_now_iso()
    runner._run_store.write_chain_run(chain_dir, chain.model_dump())

    async def _run_step(step: ChainStepSpec):
        execute_kwargs = {
            "chain": chain,
            "step": step,
            "workspace": chain.workspace,
            "workspace_root": Path(cfg["workspace_root"]),
            "entity_payload": cfg["entity_payload"],
            "llm": cfg["llm"],
            "max_payload_chars": cfg["max_payload_chars"],
            "slice_fn": cfg["slice_fn"],
            "retrieve_fn": cfg["retrieve_fn"],
            "runtime_mode_override": cfg["runtime_mode_override"],
        }
        if use_step_pipeline(step):
            return await run_step_pipeline_step(
                chain=chain,
                step=step,
                chain_dir=chain_dir,
                executor=runner._executor,  # noqa: SLF001
                workspace_root=Path(cfg["workspace_root"]),
                entity_payload=cfg["entity_payload"],
                llm=cfg["llm"],
                max_payload_chars=cfg["max_payload_chars"],
                slice_fn=cfg["slice_fn"],
                retrieve_fn=cfg["retrieve_fn"],
                runtime_mode_override=cfg["runtime_mode_override"],
            )
        return await runner._executor._execute_step(**execute_kwargs)  # noqa: SLF001

    outcomes = await asyncio.gather(
        *[
            _run_step(step)
            for step in ready_steps
            if chain.steps[step.id].status == "running"
        ]
    )

    events: list[dict[str, Any]] = []
    wave_failed = False
    for outcome in outcomes:
        step_run = chain.steps[outcome.step_id]
        step = next(item for item in chain.spec.steps if item.id == outcome.step_id)

        if outcome.contract_errors:
            step_run.status = "failed"
            step_run.error = "; ".join(outcome.contract_errors)
            wave_failed = True
        elif outcome.error:
            step_run.status = "failed"
            step_run.error = outcome.error
            wave_failed = True
        elif outcome.result is None:
            step_run.status = "failed"
            step_run.error = "step returned no result"
            wave_failed = True
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
            pipeline_gated = use_step_pipeline(step) and not outcome.error
            if not pipeline_gated and apply_step_quality_gate(
                step_run,
                finish_reason=str(outcome.result.finish_reason or ""),
                warnings=list(outcome.result.warnings or []),
                workspace_root=Path(cfg["workspace_root"]),
            ):
                wave_failed = True
            elif step_run.missing_outputs:
                step_run.status = "partial"
            elif step_run.missing_inputs:
                step_run.status = "partial"

        step_run.finished_at = utc_now_iso()
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
        events.append(
            ChainEvent(
                chain_id=chain.chain_id,
                phase="step",
                event="step_finished",
                summary=step_run.status,
                step_id=step.id,
                skill=step.skill,
                status=step_run.status,
            ).to_dict()
        )

        if wave_failed:
            chain.status = "failed"
            chain.error = f"step {outcome.step_id} failed: {step_run.error}"

    if wave_failed and chain.spec.stop_on_error:
        runner._executor._skip_pending_steps(chain, reason=chain.error)  # noqa: SLF001

    chain.updated_at = utc_now_iso()
    runner._executor._finalize_if_terminal(chain, chain.updated_at)  # noqa: SLF001
    runner._run_store.write_chain_run(chain_dir, chain.model_dump())

    emit_chain_event(
        chain_dir,
        ChainEvent(
            chain_id=chain.chain_id,
            phase="wave",
            event="wave_finished",
            summary=f"Wave complete — chain {chain.status}",
            status=chain.status,
        ),
    )

    return {
        "chain": chain.model_dump(),
        "wave_index": state["wave_index"] + 1,
        "events": events,
    }

async def _finalize_node(state: ChainGraphState, *, config: RunnableConfig) -> dict[str, Any]:
    chain = ChainRunState.model_validate(state["chain"])
    chain_dir = Path(state["chain_dir"])
    cfg = config.get("configurable") or {}
    if not chain.finished_at:
        finished = utc_now_iso()
        SkillChainExecutor._finalize_if_terminal(chain, finished)  # noqa: SLF001
        chain.updated_at = finished
        cfg["runner"]._run_store.write_chain_run(  # noqa: SLF001
            chain_dir,
            chain.model_dump(),
        )
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
    return {"chain": chain.model_dump(), "events": []}


def build_studio_graph():
    """Mission-readiness DAG for LangGraph Studio — same graph as production."""
    from src.skills.mission_readiness_chain import build_mission_readiness_chain_spec

    spec = build_mission_readiness_chain_spec("LangGraph Studio topology.")
    return build_mission_readiness_graph(spec).compile()


__all__ = [
    "LangGraphChainRunner",
    "use_langgraph_for_spec",
    "read_chain_events",
    "build_studio_graph",
]