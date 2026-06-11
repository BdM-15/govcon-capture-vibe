from dataclasses import dataclass

from src.server.chat_routes import QuerySettingsStore
from src.skills.retrieval_plan import (
    resolve_skill_retrieval_plan,
    skill_retrieval_mode_from_query,
)


@dataclass
class FakeSettings:
    workspace: str = "demo"
    enable_rerank: bool = True
    min_rerank_score: float = 0.2


def test_skill_retrieval_mode_maps_bypass_to_off() -> None:
    assert skill_retrieval_mode_from_query("bypass") == "off"
    assert skill_retrieval_mode_from_query("mix") == "mix"


def test_resolve_skill_retrieval_plan_inherits_query_settings(tmp_path) -> None:
    workspace = tmp_path / "demo"
    workspace.mkdir()
    store = QuerySettingsStore(
        workspace_dir=lambda: workspace,
        settings_provider=lambda: FakeSettings(),
    )
    store.write({**store.defaults(), "top_k": 55, "chunk_top_k": 22, "mode": "hybrid"})

    plan = resolve_skill_retrieval_plan(store.read(), "focused summary")

    assert plan.mode == "hybrid"
    assert plan.query_overrides["top_k"] == 55
    assert plan.query_overrides["chunk_top_k"] == 22
    assert plan.query_overrides["only_need_context"] is True
    assert plan.coverage_boost_applied is False


def test_resolve_skill_retrieval_plan_applies_coverage_boost(tmp_path) -> None:
    workspace = tmp_path / "demo"
    workspace.mkdir()
    store = QuerySettingsStore(
        workspace_dir=lambda: workspace,
        settings_provider=lambda: FakeSettings(),
    )

    plan = resolve_skill_retrieval_plan(
        store.read(),
        "Produce a full mapping of all task areas in this solicitation",
    )

    assert plan.coverage_boost_applied is True
    assert plan.query_overrides["top_k"] > store.read()["top_k"]