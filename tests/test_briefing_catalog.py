from __future__ import annotations

from src.server.briefing_catalog import (
    build_intel_slices_from_library,
    resolve_skill_default_prompt,
)
from src.server.briefing_prompts import BRIEFING_PROMPT_LIBRARY
from src.server.prompt_library import (
    PromptEntryUpdate,
    PromptLibraryStore,
    shipped_defaults,
)


def test_shipped_defaults_include_briefing_prompts() -> None:
    defaults = shipped_defaults()
    briefing_ids = {
        entry["slice_id"]
        for entry in defaults
        if entry.get("channel") == "briefing_skill"
    }
    assert briefing_ids == {
        "mission-readiness",
        "financial",
        "logistics",
    }
    assert len(BRIEFING_PROMPT_LIBRARY) == 8


def test_build_intel_slices_from_library_matches_catalog_shape() -> None:
    slices = build_intel_slices_from_library(shipped_defaults())
    ids = [item["id"] for item in slices]
    assert ids == [
        "overview",
        "sites",
        "evaluation",
        "mission-readiness",
        "financial",
        "logistics",
    ]

    mission = next(item for item in slices if item["id"] == "mission-readiness")
    assert mission["action"] == "skill"
    assert mission["skill"] == "mission-readiness-framer"
    assert mission["chain_preset"] == "mission-readiness"
    assert "claim_gaps" in mission["skill_prompt"]
    assert mission["prompt_library_id"]
    assert mission["related_skills"][0]["skill"] == "compliance-auditor"


def test_resolve_skill_default_prompt_for_mission_readiness_framer() -> None:
    entry = resolve_skill_default_prompt(
        shipped_defaults(),
        "mission-readiness-framer",
    )
    assert entry is not None
    assert "claim_gaps" in entry["prompt"]


def test_workspace_override_changes_intel_slice_prompt(tmp_path) -> None:
    store = PromptLibraryStore(workspace_dir=lambda: tmp_path)
    mission = store.skill_default_prompt("mission-readiness-framer")
    assert mission is not None
    store.update(
        mission["id"],
        PromptEntryUpdate(prompt="Custom mission readiness invoke prompt."),
    )

    slices = build_intel_slices_from_library(store.read())
    updated = next(item for item in slices if item["id"] == "mission-readiness")
    assert updated["skill_prompt"] == "Custom mission readiness invoke prompt."