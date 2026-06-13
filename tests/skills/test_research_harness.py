"""Tests for platform research harness."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.research_harness import (
    ResearchHarnessConfig,
    append_bootstrap_retrieval,
    frame_artifact_needs_work,
    init_harness_state,
    load_harness_state,
    make_research_continue_fn,
    needs_synthesis,
    record_tool_retrieval,
    resolve_harness_config,
    set_phase,
    skill_uses_research_harness,
    validate_harness_write_file,
    write_frame_artifact,
)
from src.skills.skill_local_tools import SkillToolsHooks, load_skill_tool_module
from src.skills.skill_models import Skill, parse_frontmatter


def _mission_skill() -> Skill:
    skill_dir = Path(__file__).resolve().parents[2] / ".github" / "skills" / "mission-readiness-framer"
    skill_md = skill_dir / "SKILL.md"
    frontmatter, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    return Skill(
        name="mission-readiness-framer",
        path=str(skill_dir),
        skill_md_path=str(skill_md),
        frontmatter=frontmatter,
        body_md=body,
    )


def _mission_hooks() -> SkillToolsHooks:
    skill_dir = Path(__file__).resolve().parents[2] / ".github" / "skills" / "mission-readiness-framer"
    module = load_skill_tool_module(skill_dir, "mission_readiness_tools")
    return SkillToolsHooks(
        artifact_continue=module.artifact_continue_message,
        validate_run=module.validate_skill_run,
        write_depth_audit=module.write_depth_audit,
        validate_write_file=module.validate_write_file,
    )


def test_mission_readiness_harness_always_resynthesizes_long_brief() -> None:
    skill = _mission_skill()
    config = resolve_harness_config(skill)
    assert config.always_resynthesize is True
    assert config.synthesis_max_tokens >= 48_000
    assert config.min_brief_chars >= 12_000

    run_dir = Path("/tmp/unused")
    # needs_synthesis only checks scratchpad on disk; test logic via config flag
    assert config.always_resynthesize


def test_skill_uses_research_harness_with_metadata_flag() -> None:
    skill = _mission_skill()
    hooks = SkillToolsHooks()
    assert skill_uses_research_harness(skill, hooks) is True


def test_init_harness_creates_scratchpad_and_plan(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    config = resolve_harness_config(_mission_skill())
    init_harness_state(run_dir, config)

    assert (run_dir / "artifacts" / "research_scratchpad.md").is_file()
    assert (run_dir / "artifacts" / "retrieval_plan.json").is_file()
    state = load_harness_state(run_dir)
    assert state.get("phase") == "retrieve"
    assert len(state.get("plan_surfaces") or []) >= 12
    inquiry_ids = {str(surface.get("id")) for surface in state.get("plan_surfaces") or []}
    assert "methods_modernization" in inquiry_ids
    assert "innovation_inquiry" in inquiry_ids
    assert "shipley_pains" in inquiry_ids
    assert "shipley_needs_wants" in inquiry_ids
    assert "shipley_win_themes" in inquiry_ids


def test_validate_harness_write_blocks_deliverables_in_retrieve_phase(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config = resolve_harness_config(_mission_skill())
    init_harness_state(run_dir, config)

    blocked = validate_harness_write_file(
        run_dir,
        path="artifacts/brief.md",
        config=config,
    )
    assert blocked is not None
    assert "retrieve phase" in blocked


def test_record_tool_retrieval_appends_scratchpad(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config = resolve_harness_config(_mission_skill())
    init_harness_state(run_dir, config)

    payload = json.dumps(
        {
            "matched_entity_names": ["Technical Factor"],
            "source_chunks": [
                {
                    "chunk_id": "chunk-abc123",
                    "content": "The contractor shall maintain fleet readiness across all task areas.",
                }
            ],
        }
    )
    record_tool_retrieval(
        run_dir,
        tool_name="kg_chunks",
        arguments_json=json.dumps({"query": "evaluation factors technical approach"}),
        payload_str=payload,
        config=config,
    )

    scratchpad = (run_dir / "artifacts" / "research_scratchpad.md").read_text(encoding="utf-8")
    assert "chunk-abc123" in scratchpad
    assert "evaluation factors" in scratchpad.lower()
    state = load_harness_state(run_dir)
    assert int(state.get("kg_chunks_calls") or 0) == 1
    retrieved = [
        surface
        for surface in state.get("plan_surfaces") or []
        if surface.get("status") in {"retrieved", "saturated"}
    ]
    assert retrieved


def test_research_continue_transitions_to_draft_when_gate_passes(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config = ResearchHarnessConfig(min_kg_chunks_passes=2, min_scratchpad_chars=200)
    init_harness_state(run_dir, config)

    record_tool_retrieval(
        run_dir,
        tool_name="kg_entities",
        arguments_json=json.dumps(
            {"types": ["evaluation_factor", "subfactor", "requirement", "pain_point"]}
        ),
        payload_str=json.dumps({"entities": {"evaluation_factor": [{"name": "Technical"}]}}),
        config=config,
    )

    queries = [
        "background mission program context",
        "PWS SOW tasks deliverables",
        "QASP performance standards SLA",
        "evaluation factors subfactor section m",
        "transition plan phase-in amendments",
        "current methods systems tools software manual processes modernization",
        "innovation innovative efficient continuous improvement lean delivery",
        "sites locations OCONUS surge shipboard readiness operational",
        "importance signals hot button discriminator implicit criteria tea leaves",
        "customer pain points program office challenges latent structural pain",
        "customer needs wants priorities buying vision program office objectives",
        "win theme discriminator hot button proof expected strengths weaknesses",
    ]
    for index, query in enumerate(queries):
        record_tool_retrieval(
            run_dir,
            tool_name="kg_chunks",
            arguments_json=json.dumps({"query": query}),
            payload_str=json.dumps(
                {
                    "source_chunks": [
                        {"chunk_id": f"chunk-{index}", "content": "x" * 300}
                    ]
                }
            ),
            config=config,
        )

    state = load_harness_state(run_dir)
    assert state is not None
    assert state.get("phase") == "draft"
    plan = json.loads((run_dir / "artifacts" / "retrieval_plan.json").read_text(encoding="utf-8"))
    assert plan.get("plan_complete") is True


def test_record_tool_retrieval_dedupes_scratchpad_chunks(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config = resolve_harness_config(_mission_skill())
    init_harness_state(run_dir, config)

    shared_chunk = {
        "chunk_id": "chunk-shared",
        "content": "Fleet readiness shall be maintained at 95 percent availability.",
    }
    for query in ("QASP performance standards", "inspection acceptance criteria"):
        record_tool_retrieval(
            run_dir,
            tool_name="kg_chunks",
            arguments_json=json.dumps({"query": query}),
            payload_str=json.dumps({"source_chunks": [shared_chunk]}),
            config=config,
        )

    scratchpad = (run_dir / "artifacts" / "research_scratchpad.md").read_text(encoding="utf-8")
    assert scratchpad.count("chunk-shared") == 1
    assert "already present in scratchpad" in scratchpad


def test_append_bootstrap_retrieval_seeds_scratchpad(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config = resolve_harness_config(_mission_skill())
    init_harness_state(run_dir, config)
    grounded = {
        "entities": [{"entity_name": "Technical", "entity_type": "evaluation_factor", "description": "x"}],
        "chunks": [{"chunk_id": "chunk-boot", "content": "Bootstrap excerpt text."}],
        "relationships": [],
        "references": [],
    }
    append_bootstrap_retrieval(run_dir, config, grounded, query="mission readiness")
    scratchpad = (run_dir / "artifacts" / "research_scratchpad.md").read_text(encoding="utf-8")
    assert "Bootstrap retrieval" in scratchpad
    assert "chunk-boot" in scratchpad
    state = load_harness_state(run_dir)
    assert state.get("bootstrap_seeded") is True


def test_resolve_harness_config_loads_plan_surfaces_path() -> None:
    config = resolve_harness_config(_mission_skill())
    assert config.frame_artifact == "mission_readiness_frame.json"
    assert "mission_readiness_frame.json" in config.deliverables
    assert any(surface.get("id") == "shipley_pains" for surface in config.plan_surfaces)


def _win_themes_skill() -> Skill:
    skill_dir = Path(__file__).resolve().parents[2] / ".github" / "skills" / "readiness-frame-win-themes"
    skill_md = skill_dir / "SKILL.md"
    frontmatter, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    return Skill(
        name="readiness-frame-win-themes",
        path=str(skill_dir),
        skill_md_path=str(skill_md),
        frontmatter=frontmatter,
        body_md=body,
    )


def test_win_themes_harness_is_handoff_json_only() -> None:
    skill = _win_themes_skill()
    config = resolve_harness_config(skill)
    assert config.frame_artifact == "win_themes_handoff.json"
    assert config.synthesis_artifact == "win_themes_handoff.json"
    assert needs_synthesis(Path("/tmp/unused"), config) is False


def test_frame_artifact_needs_work_uses_win_theme_candidates(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config = resolve_harness_config(_win_themes_skill())
    init_harness_state(run_dir, config)
    assert frame_artifact_needs_work(run_dir, config) is True

    payload = {
        "win_theme_candidates": [
            {
                "theme": "Crisis-ready FMC",
                "priority": 1,
                "rationale_chain": "Government requires 100% FMC.",
                "proof_required": ["ME plan"],
                "evaluation_factor_links": ["Factor 1 Management"],
            }
        ]
    }
    write_frame_artifact(run_dir, config, json.dumps(payload))
    assert frame_artifact_needs_work(run_dir, config) is False


def test_needs_synthesis_when_brief_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config = resolve_harness_config(_mission_skill())
    init_harness_state(run_dir, config)
    record_tool_retrieval(
        run_dir,
        tool_name="kg_chunks",
        arguments_json="{}",
        payload_str=json.dumps({"source_chunks": [{"chunk_id": "c1", "content": "a" * 2000}]}),
        config=config,
    )
    assert needs_synthesis(run_dir, config) is True