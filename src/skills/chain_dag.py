"""DAG helpers for skill-chain orchestration (wave scheduling, resume invalidation)."""

from __future__ import annotations

from src.skills.chain_models import ChainSpec, ChainStepRun


def compute_execution_waves(spec: ChainSpec) -> list[list[str]]:
    """Return topological execution waves — steps in a wave may run concurrently."""
    pending: dict[str, set[str]] = {
        step.id: set(step.depends_on) for step in spec.steps
    }
    waves: list[list[str]] = []
    finished: set[str] = set()

    while pending:
        wave = sorted(step_id for step_id, deps in pending.items() if not deps)
        if not wave:
            raise ValueError("chain spec contains a cyclic or unsatisfiable dependency graph")
        waves.append(wave)
        finished.update(wave)
        for step_id in wave:
            pending.pop(step_id, None)
        for deps in pending.values():
            deps.difference_update(finished)
    return waves


def transitive_dependent_ids(spec: ChainSpec, root_step_id: str) -> set[str]:
    """Steps that directly or indirectly depend on ``root_step_id``."""
    children: dict[str, set[str]] = {step.id: set() for step in spec.steps}
    for step in spec.steps:
        for dependency in step.depends_on:
            children.setdefault(dependency, set()).add(step.id)

    dependents: set[str] = set()
    queue = list(children.get(root_step_id, ()))
    while queue:
        step_id = queue.pop()
        if step_id in dependents:
            continue
        dependents.add(step_id)
        queue.extend(children.get(step_id, ()))
    return dependents


def ready_step_ids(
    spec: ChainSpec,
    steps: dict[str, ChainStepRun],
) -> list[str]:
    """Pending steps whose dependencies are completed or partial."""
    terminal_upstream = {"completed", "partial"}
    ready: list[str] = []
    for step in spec.steps:
        run = steps.get(step.id)
        if not run or run.status != "pending":
            continue
        if all(steps[dep].status in terminal_upstream for dep in step.depends_on):
            ready.append(step.id)
    return ready


def all_steps_terminal(steps: dict[str, ChainStepRun]) -> bool:
    terminal = {"completed", "partial", "failed", "skipped"}
    return all(run.status in terminal for run in steps.values())


__all__ = [
    "all_steps_terminal",
    "compute_execution_waves",
    "ready_step_ids",
    "transitive_dependent_ids",
]