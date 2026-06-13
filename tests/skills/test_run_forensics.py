"""Tests for skill run retrieval forensics."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.run_forensics import (
    build_run_forensics,
    format_run_forensics_report,
    write_run_forensics,
)


def _sample_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run-abc"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)

    scratchpad = "\n".join(
        [
            "# Research Scratchpad",
            "",
            "---",
            "",
            "## Retrieval pass 1 — `kg_chunks`",
            "",
            "### Query",
            "PWS SOW task areas deliverables",
            "",
            "### Source excerpts",
            "",
            "#### chunk-aaa",
            "Task area one shall maintain readiness.",
            "",
            "---",
            "",
            "## Retrieval pass 2 — `kg_chunks`",
            "",
            "### Query",
            "QASP performance standards inspection",
            "",
            "#### chunk-bbb",
            "Inspection criteria apply weekly.",
            "",
            "#### chunk-aaa",
            "duplicate should still be listed in second pass block",
        ]
    )
    (artifacts / "research_scratchpad.md").write_text(scratchpad, encoding="utf-8")
    (artifacts / "harness_state.json").write_text(
        json.dumps(
            {
                "phase": "draft",
                "kg_entities_satisfied": True,
                "kg_chunks_calls": 2,
                "scratchpad_chunk_ids": ["chunk-aaa", "chunk-bbb"],
                "plan_surfaces": [
                    {
                        "id": "pws_sow",
                        "label": "PWS",
                        "status": "retrieved",
                        "keywords": ["pws", "sow", "deliverable"],
                        "kg_chunks_attempts": 1,
                        "last_new_chunks": 1,
                    },
                    {
                        "id": "qasp",
                        "label": "QASP",
                        "status": "retrieved",
                        "keywords": ["qasp", "performance", "inspection"],
                        "kg_chunks_attempts": 1,
                        "last_new_chunks": 1,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "retrieval_plan.json").write_text(
        json.dumps({"plan_complete": True, "status": "complete"}),
        encoding="utf-8",
    )
    (artifacts / "brief.md").write_text("# Brief\n\n## Eval cross-walk\n", encoding="utf-8")
    (artifacts / "mission_readiness_frame.json").write_text(
        json.dumps({"customer_pain_points": [{"id": "PP-1"}], "eval_crosswalk": []}),
        encoding="utf-8",
    )
    transcript = [
        {
            "kind": "tool",
            "name": "kg_entities",
            "arguments": json.dumps({"types": ["evaluation_factor", "subfactor"]}),
            "extra": {},
        },
        {
            "kind": "tool",
            "name": "kg_chunks",
            "arguments": json.dumps({"query": "PWS SOW task areas deliverables"}),
            "extra": {
                "chunk_count": 1,
                "rerank": {
                    "skipped": False,
                    "top_score": 0.82,
                    "candidates": 40,
                },
            },
            "chunk_ids": ["chunk-aaa"],
        },
        {
            "kind": "tool",
            "name": "kg_chunks",
            "arguments": json.dumps({"query": "QASP performance standards inspection"}),
            "extra": {
                "chunk_count": 2,
                "rerank": {
                    "skipped": True,
                    "reason": "candidates_within_top_n",
                    "candidates": 20,
                    "top_n": 30,
                },
            },
            "chunk_ids": ["chunk-bbb", "chunk-aaa"],
        },
        {
            "kind": "tool",
            "name": "kg_chunks",
            "arguments": json.dumps({"query": "PWS SOW task areas deliverables"}),
            "extra": {"plan_guard": "duplicate", "chunk_count": 0},
            "chunk_ids": [],
        },
    ]
    (run_dir / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
    return run_dir


def test_build_run_forensics_reports_scratchpad_and_surfaces(tmp_path: Path) -> None:
    run_dir = _sample_run(tmp_path)
    payload = build_run_forensics(run_dir)

    assert payload["scratchpad"]["chars"] > 0
    assert payload["scratchpad"]["unique_chunk_ids_in_scratchpad"] == 2
    assert payload["harness"]["plan_complete"] is True
    assert payload["transcript_retrieval"]["kg_chunks_calls"] == 3
    assert payload["transcript_retrieval"]["kg_chunks_skipped"] == 1
    assert payload["transcript_retrieval"]["unique_chunk_ids_from_transcript"] == 2
    surfaces = {row["surface_id"]: row for row in payload["surfaces"]}
    assert surfaces["pws_sow"]["scratchpad_chars"] > 0
    assert surfaces["qasp"]["unique_chunks_in_scratchpad"] == 2
    assert payload["transcript_retrieval"]["rerank_summary"]["top_score_max"] == 0.82


def test_write_run_forensics_emits_json_artifact(tmp_path: Path) -> None:
    run_dir = _sample_run(tmp_path)
    payload = write_run_forensics(run_dir)
    out_path = run_dir / "artifacts" / "retrieval_forensics.json"
    assert out_path.is_file()
    assert payload.get("forensics_path") == str(out_path)
    loaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert loaded["deliverables"]["brief_chars"] > 0


def test_format_run_forensics_report_includes_rerank_hints(tmp_path: Path) -> None:
    run_dir = _sample_run(tmp_path)
    report = format_run_forensics_report(build_run_forensics(run_dir))
    assert "Retrieval forensics" in report
    assert "rerank" in report.lower()
    assert "pws_sow" in report