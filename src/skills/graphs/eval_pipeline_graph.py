"""LangGraph eval pipeline: retrieve (main LLM) -> finalize (platform) -> conditional retry."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RunnableConfig

from src.skills.chain_executor import SkillChainExecutor
from src.skills.chain_models import ChainRunState, ChainStepSpec
from src.skills.graphs.chain_events import ChainEvent, emit_chain_event
from src.skills.platform_eval_finalize import finalize_eval_handoff
from src.skills.skill_models import SkillInvocationResult

logger = logging.getLogger(__name__)

InvokeSkillCallable = Callable[..., Awaitable[SkillInvocationResult]]
_MAX_RETRIEVE_RETRIES = 2


class EvalPipelineState(TypedDict, total=False):
    chain_id: str
    chain_dir: str
    step_id: str
    retry_count: int
    run_id: str
    run_dir: str
    response: str
    finish_reason: str
    warnings: list[str]
    gate_issues: list[str]
    status: str
    elapsed_ms: int


@dataclass(frozen=True)
class EvalPipelineOutcome:
    step_id: str
    result: SkillInvocationResult | None
    error: str = ""
    contract_errors: list[str] | None = None


def build_eval_pipeline_graph():
    graph = StateGraph(EvalPipelineState)
    graph.add_node("retrieve", _retrieve_node)
    graph.add_node("finalize", _finalize_node)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "finalize")
    graph.add_conditional_edges(
        "finalize",
        _route_after_finalize,
        {"retrieve": "retrieve", "done": END},
    )
    return graph


def _route_after_finalize(state: EvalPipelineState) -> str:
    if state.get("status") == "completed":
        return "done"
    retries = int(state.get("retry_count") or 0)
    if state.get("status") == "retry" and retries < _MAX_RETRIEVE_RETRIES:
        return "retrieve"
    return "done"


async def _retrieve_node(state: EvalPipelineState, *, config: RunnableConfig) -> dict[str, Any]:
    cfg = config.get("configurable") or {}
    chain = ChainRunState.model_validate(cfg["chain"])
    step: ChainStepSpec = cfg["step"]
    chain_dir = Path(state["chain_dir"])
    retry = int(state.get("retry_count") or 0)

    emit_chain_event(
        chain_dir,
        ChainEvent(
            chain_id=chain.chain_id,
            phase="eval_pipeline",
            event="eval_retrieve_started",
            summary=f"Eval retrieve pass {retry + 1}",
            step_id=step.id,
            skill=step.skill,
            status="running",
            detail={"retry": retry},
        ),
    )

    executor: SkillChainExecutor = cfg["executor"]
    step_to_run = step
    prior_gaps = [str(item).strip() for item in (state.get("gate_issues") or []) if str(item).strip()]
    if retry > 0 and prior_gaps:
        ctx = dict(step.context or {})
        ctx["retrieve_retry"] = retry
        ctx["platform_gate_gaps"] = prior_gaps[:12]
        step_to_run = step.model_copy(update={"context": ctx})

    outcome = await executor._execute_step(  # noqa: SLF001
        chain,
        step=step_to_run,
        workspace=chain.workspace,
        workspace_root=Path(cfg["workspace_root"]),
        entity_payload=cfg["entity_payload"],
        llm=cfg["llm"],
        max_payload_chars=cfg.get("max_payload_chars"),
        slice_fn=cfg.get("slice_fn"),
        retrieve_fn=cfg.get("retrieve_fn"),
        runtime_mode_override=cfg.get("runtime_mode_override"),
    )

    warnings = list(state.get("warnings") or [])
    if outcome.error:
        return {
            "status": "failed",
            "gate_issues": [outcome.error],
            "warnings": warnings,
            "retry_count": retry,
        }

    result = outcome.result
    if result is None:
        return {
            "status": "failed",
            "gate_issues": ["eval retrieve returned no result"],
            "warnings": warnings,
            "retry_count": retry,
        }

    warnings.extend(result.warnings or [])
    return {
        "run_id": result.run_id,
        "run_dir": result.run_dir,
        "response": result.response,
        "finish_reason": result.finish_reason,
        "warnings": warnings,
        "elapsed_ms": int(result.elapsed_ms or 0),
        "retry_count": retry,
    }


async def _finalize_node(state: EvalPipelineState, *, config: RunnableConfig) -> dict[str, Any]:
    cfg = config.get("configurable") or {}
    chain_dir = Path(state["chain_dir"])
    chain = ChainRunState.model_validate(cfg["chain"])
    step: ChainStepSpec = cfg["step"]
    run_dir = str(state.get("run_dir") or "").strip()
    if not run_dir:
        return {
            "status": "failed",
            "gate_issues": ["eval finalize: missing run_dir from retrieve"],
        }

    emit_chain_event(
        chain_dir,
        ChainEvent(
            chain_id=chain.chain_id,
            phase="eval_pipeline",
            event="eval_finalize_started",
            summary="Platform expand + acronym + gate",
            step_id=step.id,
            skill=step.skill,
            status="running",
        ),
    )

    workspace_root = Path(cfg["workspace_root"])
    finalize = await finalize_eval_handoff(
        run_dir=Path(run_dir),
        workspace_dir=workspace_root,
        loop_response=str(state.get("response") or ""),
    )
    warnings = list(state.get("warnings") or [])
    warnings.extend(finalize.get("warnings") or [])

    if finalize.get("passed"):
        emit_chain_event(
            chain_dir,
            ChainEvent(
                chain_id=chain.chain_id,
                phase="eval_pipeline",
                event="eval_gate_passed",
                summary="Eval handoff passed platform gate",
                step_id=step.id,
                skill=step.skill,
                status="completed",
            ),
        )
        return {
            "status": "completed",
            "gate_issues": [],
            "warnings": warnings,
            "finish_reason": "stop",
        }

    blocking = finalize.get("blocking_issues") or []
    retriable = finalize.get("retriable_issues") or []
    all_issues = finalize.get("issues") or []

    if blocking:
        return {
            "status": "failed",
            "gate_issues": blocking,
            "warnings": warnings,
            "finish_reason": "depth_incomplete",
        }

    retry = int(state.get("retry_count") or 0)
    if retriable and retry < _MAX_RETRIEVE_RETRIES:
        emit_chain_event(
            chain_dir,
            ChainEvent(
                chain_id=chain.chain_id,
                phase="eval_pipeline",
                event="eval_gate_retry",
                summary=f"Coverage/substance gap — retrieve retry {retry + 1}",
                step_id=step.id,
                skill=step.skill,
                status="running",
                detail={"issues": retriable[:6]},
            ),
        )
        return {
            "status": "retry",
            "gate_issues": retriable,
            "warnings": warnings,
            "retry_count": retry + 1,
            "finish_reason": "depth_incomplete",
        }

    return {
        "status": "failed",
        "gate_issues": all_issues,
        "warnings": warnings,
        "finish_reason": "depth_incomplete",
    }


async def run_eval_pipeline_step(
    *,
    chain: ChainRunState,
    step: ChainStepSpec,
    chain_dir: Path,
    executor: SkillChainExecutor,
    workspace_root: Path,
    entity_payload: dict[str, Any],
    llm: Any,
    max_payload_chars: Optional[int] = None,
    slice_fn: Any = None,
    retrieve_fn: Any = None,
    runtime_mode_override: Optional[str] = None,
) -> EvalPipelineOutcome:
    """Run eval as LangGraph subgraph (retrieve -> finalize -> conditional retry)."""
    graph = build_eval_pipeline_graph()
    compiled = graph.compile()

    run_config = {
        "configurable": {
            "chain": chain.model_dump(),
            "step": step,
            "executor": executor,
            "workspace_root": str(workspace_root),
            "entity_payload": entity_payload,
            "llm": llm,
            "max_payload_chars": max_payload_chars,
            "slice_fn": slice_fn,
            "retrieve_fn": retrieve_fn,
            "runtime_mode_override": runtime_mode_override,
        }
    }

    final_state = await compiled.ainvoke(
        {
            "chain_id": chain.chain_id,
            "chain_dir": str(chain_dir),
            "step_id": step.id,
            "retry_count": 0,
            "warnings": [],
        },
        config=run_config,
    )

    status = str(final_state.get("status") or "failed")
    run_id = str(final_state.get("run_id") or "")
    run_dir = str(final_state.get("run_dir") or "")
    warnings = list(final_state.get("warnings") or [])
    finish_reason = str(final_state.get("finish_reason") or "stop")
    gate_issues = list(final_state.get("gate_issues") or [])

    if status == "completed" and run_id and run_dir:
        result = SkillInvocationResult(
            skill=step.skill,
            workspace=chain.workspace,
            response=str(final_state.get("response") or "eval pipeline complete"),
            entities_used=[],
            warnings=warnings,
            elapsed_ms=int(final_state.get("elapsed_ms") or 0),
            prompt_tokens_estimate=0,
            run_id=run_id,
            run_dir=run_dir,
            finish_reason=finish_reason,
        )
        return EvalPipelineOutcome(step_id=step.id, result=result)

    error = "; ".join(gate_issues[:6]) if gate_issues else f"eval pipeline {status}"
    if len(gate_issues) > 6:
        error += f"; …and {len(gate_issues) - 6} more"
    return EvalPipelineOutcome(step_id=step.id, result=None, error=error)