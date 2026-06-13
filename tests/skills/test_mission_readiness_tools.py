"""Tests for mission-readiness-framer deterministic helpers."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.skill_local_tools import load_skill_tool_module


def _helpers():
    skill_dir = Path(__file__).resolve().parents[2] / ".github" / "skills" / "mission-readiness-framer"
    return load_skill_tool_module(skill_dir, "mission_readiness_tools")


def _write_harness_plan_complete(run_dir: Path) -> None:
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    surfaces = [
        {"id": "background", "status": "retrieved"},
        {"id": "pws_sow", "status": "retrieved"},
        {"id": "qasp", "status": "retrieved"},
        {"id": "evaluation", "status": "retrieved"},
        {"id": "transition", "status": "retrieved"},
        {"id": "methods_modernization", "status": "retrieved"},
        {"id": "innovation_inquiry", "status": "retrieved"},
        {"id": "operational_mission", "status": "retrieved"},
        {"id": "tea_leaves", "status": "retrieved"},
        {"id": "shipley_pains", "status": "retrieved"},
        {"id": "shipley_needs_wants", "status": "retrieved"},
        {"id": "shipley_win_themes", "status": "retrieved"},
    ]
    (artifacts / "harness_state.json").write_text(
        json.dumps(
            {
                "phase": "draft",
                "kg_entities_satisfied": True,
                "plan_surfaces": surfaces,
            }
        ),
        encoding="utf-8",
    )


def _write_retrieval_transcript(
    run_dir: Path,
    *,
    kg_chunks_calls: int = 12,
    eval_entities: int = 3,
    web_calls: int = 0,
) -> None:
    entries: list[dict] = [
        {
            "kind": "tool",
            "name": "kg_entities",
            "arguments": json.dumps(
                {
                    "types": [
                        "evaluation_factor",
                        "subfactor",
                        "requirement",
                    ]
                }
            ),
            "extra": {
                "entity_counts_by_type": {
                    "evaluation_factor": eval_entities,
                    "subfactor": 0,
                }
            },
        }
    ]
    for _ in range(kg_chunks_calls):
        entries.append(
            {
                "kind": "tool",
                "name": "kg_chunks",
                "arguments": json.dumps({"query": "package surface"}),
                "extra": {"chunk_count": 8},
            }
        )
    for _ in range(web_calls):
        entries.append({"kind": "tool", "name": "web_fetch", "arguments": "{}"})
    (run_dir / "transcript.json").write_text(json.dumps(entries), encoding="utf-8")


def test_detect_capability_overlay_request_finds_vendor_and_url() -> None:
    helpers = _helpers()
    overlay = helpers.detect_capability_overlay_request(
        "Can Tagup, Inc with their Manifest platform help? Review: https://tagup.ai/platform"
    )
    assert overlay is not None
    assert "tagup.ai/platform" in overlay["urls"][0]
    assert "Tagup" in overlay["vendor"]


def test_validate_mission_readiness_run_flags_thin_crosswalk_and_overlay(tmp_path: Path) -> None:
    helpers = _helpers()
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "brief.md").write_text("# Brief\n\n## Eval cross-walk\n\n| a | b |\n", encoding="utf-8")
    (artifacts / "mission_readiness_frame.json").write_text(
        json.dumps(
            {
                "customer_pain_points": [{"id": "PP-001"}],
                "current_methods": [],
                "innovation_opportunities": [],
                "importance_signals": [],
                "implicit_criteria": [],
                "win_theme_candidates": [],
                "verbatim_extracts": [],
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Technical",
                        "pws_clusters": ["PWS 3"],
                        "readiness_link": "too short",
                        "proof_expected": "x",
                        "source_chunk_ids": [],
                    }
                ],
                "clarification_questions": [],
            }
        ),
        encoding="utf-8",
    )

    _write_retrieval_transcript(run_dir, web_calls=1)
    _write_harness_plan_complete(run_dir)

    issues = helpers.validate_mission_readiness_run(
        run_dir,
        user_prompt="Review https://tagup.ai/platform for Tagup, Inc applicability",
    )

    assert not any("minimum" in issue.lower() for issue in issues)
    assert not any("retrieval incomplete" in issue for issue in issues)
    assert any("eval_crosswalk row 1 readiness_link missing or placeholder" in issue for issue in issues)
    assert any("capability_overlay is missing" in issue for issue in issues)
    assert any("missing substantive Capability overlay section" in issue for issue in issues)

    audit_path = helpers.write_depth_audit(run_dir, issues)
    assert audit_path.is_file()
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["issue_count"] == len(issues)


def test_validate_mission_readiness_run_does_not_flag_small_solicitation_counts(tmp_path: Path) -> None:
    helpers = _helpers()
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "brief.md").write_text(
        "\n".join(
            [
                "# Brief",
                "",
                "## Eval cross-walk",
                "",
                "| Factor | Proof |",
                "| --- | --- |",
                "| Technical | Past performance evidence |",
            ]
        ),
        encoding="utf-8",
    )
    (artifacts / "mission_readiness_frame.json").write_text(
        json.dumps(
            {
                "customer_pain_points": [{"id": "PP-001", "text": "One pain"}],
                "current_methods": [],
                "innovation_opportunities": [],
                "importance_signals": [],
                "implicit_criteria": [],
                "win_theme_candidates": [],
                "verbatim_extracts": [],
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Technical",
                        "pws_clusters": ["PWS 3"],
                        "readiness_link": "Weak technical proof would leave readiness gaps across sustainment tasks.",
                        "proof_expected": "Demonstrated technical approach with metrics.",
                        "source_chunk_ids": ["chunk-1"],
                    }
                ],
                "clarification_questions": [],
            }
        ),
        encoding="utf-8",
    )
    _write_retrieval_transcript(run_dir, eval_entities=1)
    _write_harness_plan_complete(run_dir)

    issues = helpers.validate_mission_readiness_run(run_dir)

    assert issues == []


def test_has_eval_crosswalk_section_accepts_numbered_heading() -> None:
    helpers = _helpers()
    brief = "# Brief\n\n## 5. Eval Cross-Walk\n\n| Factor | Proof |\n"
    assert helpers._has_eval_crosswalk_section(brief) is True


def test_validate_write_file_blocks_deliverables_before_retrieval(tmp_path: Path) -> None:
    helpers = _helpers()
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)

    blocked = helpers.validate_write_file(
        run_dir,
        path="artifacts/brief.md",
        content="# Brief",
        user_prompt="Build the Mission Readiness Frame",
    )
    assert blocked is not None
    assert "write_file blocked" in blocked

    _write_retrieval_transcript(run_dir)
    allowed = helpers.validate_write_file(
        run_dir,
        path="artifacts/brief.md",
        content="# Brief",
    )
    assert allowed is None


def test_artifact_continue_message_nudges_thin_completed_run(tmp_path: Path) -> None:
    helpers = _helpers()
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "brief.md").write_text(
        "\n".join(
            [
                "# Brief",
                "",
                "## 5. Eval Cross-Walk",
                "",
                "| Factor | Proof |",
                "| --- | --- |",
                "| Technical | Evidence |",
            ]
        ),
        encoding="utf-8",
    )
    (artifacts / "mission_readiness_frame.json").write_text(
        json.dumps(
            {
                "customer_pain_points": [{"id": "PP-001"}],
                "current_methods": [],
                "innovation_opportunities": [],
                "importance_signals": [],
                "implicit_criteria": [],
                "win_theme_candidates": [],
                "verbatim_extracts": [],
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Technical",
                        "pws_clusters": ["PWS 3"],
                        "readiness_link": "too short",
                        "proof_expected": "x",
                        "source_chunk_ids": [],
                    }
                ],
                "clarification_questions": [],
            }
        ),
        encoding="utf-8",
    )
    _write_retrieval_transcript(run_dir, eval_entities=4)

    message = helpers.artifact_continue_message(run_dir)
    assert message is not None
    assert "do NOT finalize" in message
    assert "eval_crosswalk under-covers" in message or "readiness_link" in message


def test_validate_flags_padded_crosswalk_and_thin_capture_sections(tmp_path: Path) -> None:
    helpers = _helpers()
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    shared_chunk = "chunk-5299cdff54e8ebf39576010b6e6a2f61"
    crosswalk = []
    for index in range(18):
        crosswalk.append(
            {
                "evaluation_factor": f"Factor {index + 1}",
                "pws_clusters": ["PWS 2.0"],
                "readiness_link": "Weak approach would leave readiness gaps across sustainment tasks.",
                "proof_expected": "Demonstrated methodology with metrics and staffing detail.",
                "source_chunk_ids": [shared_chunk],
            }
        )
    for label in (
        "Best Value Tradeoff Methodology",
        "Source Selection Decision Document",
        "Evaluation Strengths",
    ):
        crosswalk.append(
            {
                "evaluation_factor": label,
                "pws_clusters": ["All"],
                "readiness_link": "Meta label should not be a separate crosswalk row.",
                "proof_expected": "N/A",
                "source_chunk_ids": [shared_chunk],
            }
        )
    (artifacts / "mission_readiness_frame.json").write_text(
        json.dumps(
            {
                "customer_pain_points": [{"id": "PP-001", "text": "One pain"}],
                "current_methods": [{"id": "CM-001"}],
                "innovation_opportunities": [{"id": "IO-001"}],
                "importance_signals": [{"id": "IS-001"}],
                "implicit_criteria": [{"id": "IC-001"}],
                "win_theme_candidates": [{"id": "WT-001"}],
                "verbatim_extracts": [{"id": "VE-001"}],
                "eval_crosswalk": crosswalk,
                "clarification_questions": [],
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "brief.md").write_text(
        "# Brief\n\n## Eval cross-walk\n\n| Factor | Proof |\n| --- | --- |",
        encoding="utf-8",
    )
    _write_retrieval_transcript(run_dir, eval_entities=40)
    _write_harness_plan_complete(run_dir)
    harness_state = json.loads((artifacts / "harness_state.json").read_text(encoding="utf-8"))
    harness_state["scratchpad_chars"] = 300_000
    (artifacts / "harness_state.json").write_text(
        json.dumps(harness_state),
        encoding="utf-8",
    )

    issues = helpers.validate_mission_readiness_run(run_dir)

    assert any("customer_pain_points" in issue for issue in issues)
    assert any("verbatim_extracts" in issue for issue in issues)
    assert any("over-relies on one source chunk" in issue for issue in issues)


def test_transcript_tool_stats_uses_peak_eval_count_not_sum() -> None:
    helpers = _helpers()
    transcript = [
        {
            "kind": "tool",
            "name": "kg_entities",
            "arguments": json.dumps({"types": ["evaluation_factor", "subfactor"]}),
            "extra": {"entity_counts_by_type": {"evaluation_factor": 19, "subfactor": 8}},
        },
        {
            "kind": "tool",
            "name": "kg_entities",
            "arguments": json.dumps({"types": ["evaluation_factor"]}),
            "extra": {"entity_counts_by_type": {"evaluation_factor": 40}},
        },
        {
            "kind": "tool",
            "name": "kg_entities",
            "arguments": json.dumps({"types": ["evaluation_factor"]}),
            "extra": {"entity_counts_by_type": {"evaluation_factor": 40}},
        },
    ]
    stats = helpers._transcript_tool_stats(transcript)
    assert stats["eval_entities_retrieved"] == 40


def test_ensure_minimum_frame_logs_missing_eval_factors_without_scaffold_rows(tmp_path: Path) -> None:
    helpers = _helpers()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "vdb_entities.json").write_text(
        json.dumps(
            {
                "data": [
                    {
                        "entity_type": "evaluation_factor",
                        "entity_name": "Factor 1 Management",
                        "content": "Factor 1 Management evaluates org structure and transition.",
                    },
                    {
                        "entity_type": "subfactor",
                        "entity_name": "Organizational Structure",
                        "content": "Organizational Structure subfactor under Factor 1.",
                    },
                    {
                        "entity_type": "evaluation_factor",
                        "entity_name": "Rating Scale Definitions",
                        "content": "Adjectival rating scale methodology",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "harness_state.json").write_text(
        json.dumps({"scratchpad_chunk_ids": ["chunk-abc123"]}),
        encoding="utf-8",
    )

    frame_path = helpers.ensure_minimum_frame(run_dir, workspace)
    assert frame_path is not None
    payload = json.loads(frame_path.read_text(encoding="utf-8"))
    assert payload.get("eval_crosswalk") == []
    gaps = payload.get("claim_gaps") or []
    assert isinstance(gaps, list)
    gap_text = " ".join(str(item) for item in gaps).lower()
    assert "factor 1 management" in gap_text
    assert "organizational structure" in gap_text
    assert "rating scale definitions" not in gap_text
    assert "auto-scaffolded" not in gap_text


def test_validate_mission_readiness_run_flags_boilerplate_crosswalk(tmp_path: Path) -> None:
    helpers = _helpers()
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "brief.md").write_text(
        "\n".join(
            [
                "# Brief",
                "",
                "## Eval cross-walk",
                "",
                "| Factor | Proof |",
                "| --- | --- |",
                "| Technical | Evidence |",
            ]
        ),
        encoding="utf-8",
    )
    (artifacts / "mission_readiness_frame.json").write_text(
        json.dumps(
            {
                "customer_pain_points": [{"id": "PP-001", "text": "One pain"}],
                "current_methods": [],
                "innovation_opportunities": [],
                "importance_signals": [],
                "implicit_criteria": [],
                "win_theme_candidates": [],
                "verbatim_extracts": [],
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Technical",
                        "pws_clusters": [
                            "Section M / PWS task clusters — refine during capture review"
                        ],
                        "readiness_link": (
                            "Proposal must demonstrate compliant approach, staffing, and proof."
                        ),
                        "proof_expected": (
                            "Proposal must demonstrate compliant approach, staffing, and proof."
                        ),
                        "source_chunk_ids": ["chunk-1"],
                    }
                ],
                "clarification_questions": [],
            }
        ),
        encoding="utf-8",
    )
    _write_retrieval_transcript(run_dir, eval_entities=1)
    _write_harness_plan_complete(run_dir)

    issues = helpers.validate_mission_readiness_run(run_dir)

    assert any("boilerplate" in issue.lower() for issue in issues)