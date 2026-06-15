"""Tests for deterministic readiness handoff merge."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.mission_readiness_merge import (
    merge_handoff_payloads,
    merge_upstream_handoffs,
    normalize_compiler_frame_envelope,
    normalize_eval_crosswalk_row,
    persist_normalized_compiler_frame,
    prepare_compiler_harness_state,
    refresh_compiler_claim_gaps_section,
    refresh_compiler_verbatim_section,
    seed_verbatim_extracts_from_citations,
    write_compiler_brief_scaffold,
)
from src.skills.research_harness import load_harness_state, resolve_harness_config
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


def test_normalize_eval_crosswalk_row_maps_evaluation_crosswalk() -> None:
    row = normalize_eval_crosswalk_row(
        {
            "factor": "Factor 1 Management",
            "subfactor": "Organizational Structure Subfactor",
            "evaluation_crosswalk": "Program office evaluates organizational integration for readiness.",
            "source_chunk_ids": ["chunk-abc"],
        }
    )
    assert "organizational integration" in row["readiness_link"].lower()
    assert row["proof_expected"]


def test_normalize_eval_crosswalk_row_fills_empty_contract_fields() -> None:
    row = normalize_eval_crosswalk_row(
        {
            "evaluation_factor": "Factor 1 Management",
            "readiness_link": "",
            "proof_expected": "",
            "evaluation_crosswalk": "Program office evaluates organizational integration for readiness.",
            "source_chunk_ids": ["chunk-abc"],
        }
    )
    assert "organizational integration" in row["readiness_link"].lower()
    assert row["proof_expected"]


def test_normalize_eval_crosswalk_row_maps_legacy_fields() -> None:
    row = normalize_eval_crosswalk_row(
        {
            "factor": "Factor 1 Management",
            "subfactor": "Organizational Structure Subfactor",
            "plain_reasoning": "Program office evaluates offeror organizational structure for clear integration.",
            "source_chunk_ids": ["chunk-abc"],
        }
    )
    assert row["evaluation_factor"] == "Factor 1 Management — Organizational Structure Subfactor"
    assert "organizational structure" in row["readiness_link"].lower()
    assert row["source_chunk_ids"] == ["chunk-abc"]


def test_merge_handoff_payloads_ensures_empty_required_arrays() -> None:
    merged = merge_handoff_payloads({"eval": {"eval_crosswalk": []}})
    assert merged["verbatim_extracts"] == []
    assert merged["clarification_questions"] == []
    assert merged["claim_gaps"] == []


def test_normalize_compiler_frame_envelope_fills_missing_lists() -> None:
    normalized = normalize_compiler_frame_envelope({"eval_crosswalk": []})
    assert normalized["verbatim_extracts"] == []
    assert normalized["clarification_questions"] == []


def test_persist_normalized_compiler_frame_writes_lists(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "chain_context.json").write_text(
        json.dumps({"role": "compiler"}),
        encoding="utf-8",
    )
    (artifacts / "mission_readiness_frame.json").write_text(
        json.dumps({"eval_crosswalk": [], "claim_gaps": ["gap"]}),
        encoding="utf-8",
    )
    assert persist_normalized_compiler_frame(run_dir) is True
    frame = json.loads((artifacts / "mission_readiness_frame.json").read_text(encoding="utf-8"))
    assert frame["verbatim_extracts"] == []
    assert frame["clarification_questions"] == []


def test_merge_handoff_payloads_unions_slices() -> None:
    merged = merge_handoff_payloads(
        {
            "eval": {
                "eval_crosswalk": [
                    {
                        "factor": "Factor 2 Technical",
                        "subfactor": "Approach",
                        "plain_reasoning": "Evaluates technical methodology depth for readiness sustainment.",
                        "source_chunk_ids": ["chunk-1"],
                    }
                ],
                "claim_gaps": ["Gap A"],
            },
            "pains": {
                "customer_pain_points": [{"id": "PP-1", "text": "Staffing surge risk"}],
                "claim_gaps": ["Gap B"],
            },
            "tea_leaves": {
                "tea_leaves": {
                    "importance_signals": [{"signal": "100% PO attainment", "confidence": "high"}],
                    "implicit_criteria": [{"criterion": "Independent QC", "confidence": "high"}],
                }
            },
            "modernization": {
                "current_methods": [{"name": "QMSS", "fit_to_scope": "high"}],
                "innovation_opportunities": [{"theme": "Predictive maintenance"}],
            },
            "win_themes": {
                "win_theme_candidates": [{"theme_id": "WT-1", "theme_name": "Integrated org"}],
            },
            "workload": {
                "mission_readiness_frame": {
                    "readiness_outcome": "Sustained readiness outcome",
                    "failure_modes_feared": [{"mode": "Transition loss"}],
                }
            },
        }
    )

    assert merged["readiness_outcome"] == "Sustained readiness outcome"
    assert len(merged["eval_crosswalk"]) == 1
    assert merged["eval_crosswalk"][0]["evaluation_factor"] == "Factor 2 Technical — Approach"
    assert len(merged["customer_pain_points"]) == 1
    assert len(merged["importance_signals"]) == 1
    assert len(merged["win_theme_candidates"]) == 1
    assert "Gap A" in merged["claim_gaps"]
    assert "Gap B" in merged["claim_gaps"]


def test_merge_upstream_handoffs_writes_frame_and_chain_context(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    artifacts = upstream / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "eval_handoff.json").write_text(
        json.dumps(
            {
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Factor 1 Management",
                        "readiness_link": "Weak management degrades readiness across sustainment tasks.",
                        "proof_expected": "Org chart and transition plan aligned to Section L.",
                        "pws_clusters": ["PWS 2.1"],
                        "source_chunk_ids": ["chunk-1"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    run_dir = tmp_path / "compile_run"
    run_dir.mkdir()
    (run_dir / "artifacts").mkdir()

    report = merge_upstream_handoffs(
        [
            {
                "step_id": "eval",
                "skill": "readiness-frame-eval",
                "run_id": "run-1",
                "filename": "eval_handoff.json",
                "path": str(artifacts / "eval_handoff.json"),
            }
        ],
        run_dir,
        chain_step_context={"role": "compiler", "slice": "compile"},
    )

    frame = json.loads((run_dir / "artifacts" / "mission_readiness_frame.json").read_text(encoding="utf-8"))
    chain_ctx = json.loads((run_dir / "artifacts" / "chain_context.json").read_text(encoding="utf-8"))
    assert report["handoffs_loaded"] == 1
    assert report["eval_crosswalk_rows"] == 1
    assert len(frame["eval_crosswalk"]) == 1
    assert chain_ctx["role"] == "compiler"
    assert (run_dir / "artifacts" / "research_scratchpad.md").is_file()
    brief = (run_dir / "artifacts" / "brief.md").read_text(encoding="utf-8")
    assert "## 5. Evaluation Cross-Walk Table" in brief
    assert "Factor 1 Management" in brief
    assert "## 8. Clarification Questions + Claim Gaps" in brief


def test_write_compiler_brief_scaffold_includes_eval_crosswalk_section(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    merged = {
        "readiness_outcome": "100% FMC sustainment.",
        "eval_crosswalk": [
            {
                "evaluation_factor": "Factor 1 Management",
                "readiness_link": "Management quality drives readiness continuity.",
                "proof_expected": "Transition and org plan.",
                "source_chunk_ids": ["chunk-abc"],
            }
        ],
        "claim_gaps": ["Missing QASP thresholds"],
        "win_theme_candidates": [{"theme": "Zero-fail FMC", "priority": 1}],
    }
    write_compiler_brief_scaffold(run_dir, merged=merged)
    brief = (artifacts / "brief.md").read_text(encoding="utf-8")
    assert "Evaluation Cross-Walk" in brief
    assert "chunk-abc" in brief
    assert "Missing QASP thresholds" in brief
    assert "Zero-fail FMC" in brief


def test_refresh_compiler_claim_gaps_section_lists_all_gaps(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "mission_readiness_frame.json").write_text(
        json.dumps({"claim_gaps": ["Gap alpha one", "Gap beta two", "Gap gamma three"]}),
        encoding="utf-8",
    )
    (artifacts / "brief.md").write_text(
        "## 8. Clarifications / Missing-Coverage Section\n\n- partial gap only\n",
        encoding="utf-8",
    )
    refresh_compiler_claim_gaps_section(run_dir)
    brief = (artifacts / "brief.md").read_text(encoding="utf-8")
    assert "Gap alpha one" in brief
    assert "Gap beta two" in brief
    assert "Gap gamma three" in brief


def test_resolve_harness_config_compiler_mode_skips_surfaces() -> None:
    skill = _mission_skill()
    standalone = resolve_harness_config(skill)
    compiler = resolve_harness_config(
        skill,
        {"chain_step_context": {"role": "compiler"}},
    )
    assert len(standalone.plan_surfaces) >= 12
    assert compiler.plan_surfaces == ()
    assert compiler.min_kg_chunks_passes == 0
    assert compiler.max_reflexion_passes == 3
    assert compiler.scratchpad_max_chars >= 500_000


def test_merge_upstream_handoffs_includes_upstream_scratchpads(tmp_path: Path) -> None:
    eval_run = tmp_path / "eval_run" / "artifacts"
    eval_run.mkdir(parents=True)
    (eval_run / "eval_handoff.json").write_text(
        json.dumps(
            {
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Factor 1 Management Approach",
                        "readiness_link": "x" * 60,
                        "proof_expected": "y" * 30,
                        "source_chunk_ids": ["chunk-abc"],
                    }
                ],
                "claim_gaps": [],
            }
        ),
        encoding="utf-8",
    )
    (eval_run / "research_scratchpad.md").write_text(
        "PWS task cluster alpha with chunk-abc evidence.\n" * 200,
        encoding="utf-8",
    )
    compile_run = tmp_path / "compile_run"
    attached = [
        {
            "filename": "eval_handoff.json",
            "path": str(eval_run / "eval_handoff.json"),
            "run_id": "eval-run-1",
            "step_id": "eval",
            "skill": "readiness-frame-eval",
        }
    ]
    merge_upstream_handoffs(attached, compile_run)
    scratchpad = (compile_run / "artifacts" / "research_scratchpad.md").read_text(
        encoding="utf-8"
    )
    assert "Upstream retrieval: eval" in scratchpad
    assert "PWS task cluster alpha" in scratchpad
    assert len(scratchpad) > 5_000


def test_seed_verbatim_extracts_from_citations_pulls_crosswalk_quotes() -> None:
    payload = {
        "verbatim_extracts": [],
        "eval_crosswalk": [
            {
                "evaluation_factor": "Factor 1 Management",
                "source_citations": [
                    {
                        "chunk_id": "chunk-abc",
                        "section": "Section M Factor 1",
                        "quote": "The Government will evaluate the offeror's management approach for continuity.",
                    }
                ],
            },
            {
                "evaluation_factor": "Factor 2 Technical",
                "source_citations": [
                    {
                        "chunk_id": "chunk-def",
                        "quote": "Offerors shall demonstrate a technical methodology aligned to PWS maintenance tasks.",
                    }
                ],
            },
        ],
    }
    seeded = seed_verbatim_extracts_from_citations(payload)
    assert len(seeded["verbatim_extracts"]) == 2
    assert seeded["verbatim_extracts"][0]["id"] == "VE-001"
    assert "management approach" in seeded["verbatim_extracts"][0]["quote"]


def test_seed_verbatim_extracts_from_citations_skips_when_populated() -> None:
    payload = {
        "verbatim_extracts": [{"id": "VE-001", "quote": "Existing government phrase retained."}],
        "eval_crosswalk": [
            {
                "source_citations": [
                    {"quote": "This quote should not replace the existing verbatim bank."}
                ]
            }
        ],
    }
    seeded = seed_verbatim_extracts_from_citations(payload)
    assert len(seeded["verbatim_extracts"]) == 1
    assert seeded["verbatim_extracts"][0]["quote"].startswith("Existing")


def test_refresh_compiler_verbatim_section_updates_brief_section_two(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "brief.md").write_text(
        "\n".join(
            [
                "# Brief",
                "## 2. Verbatim Signal Bank (Government Language)",
                "_None recorded in merged handoffs._",
                "## 3. Customer Pain Points & Importance Signals",
                "body",
            ]
        ),
        encoding="utf-8",
    )
    refresh_compiler_verbatim_section(
        run_dir,
        payload={
            "verbatim_extracts": [
                {"quote": "Government shall maintain 100 percent mission-capable readiness."}
            ]
        },
    )
    brief = (artifacts / "brief.md").read_text(encoding="utf-8")
    assert "100 percent mission-capable" in brief
    assert "_None recorded" not in brief


def test_prepare_compiler_harness_state_marks_retrieval_complete(tmp_path: Path) -> None:
    from src.skills.research_harness import init_harness_state

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    config = resolve_harness_config(_mission_skill())
    init_harness_state(run_dir, config)
    prepare_compiler_harness_state(run_dir, scratchpad_chars=25_000)
    state = load_harness_state(run_dir)
    assert state is not None
    assert state.get("phase") == "draft"
    assert state.get("kg_entities_satisfied") is True
    assert state["plan_surfaces"][0]["status"] == "retrieved"