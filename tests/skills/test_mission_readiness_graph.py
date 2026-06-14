"""Tests for full mission-readiness LangGraph DAG."""

from __future__ import annotations

from src.skills.graphs.mission_readiness_graph import build_mission_readiness_graph
from src.skills.mission_readiness_chain import build_mission_readiness_chain_spec


def test_mission_readiness_graph_has_step_nodes_and_finalize() -> None:
    spec = build_mission_readiness_chain_spec("Build MRF.")
    compiled = build_mission_readiness_graph(spec).compile()
    nodes = set(compiled.get_graph().nodes)
    step_ids = {step.id for step in spec.steps}
    assert step_ids.issubset(nodes)
    assert "chain_finalize" in nodes
    edges = {(e.source, e.target) for e in compiled.get_graph().edges}
    assert ("__start__", "eval") in edges
    assert ("__start__", "workload") in edges
    assert ("compile", "chain_finalize") in edges