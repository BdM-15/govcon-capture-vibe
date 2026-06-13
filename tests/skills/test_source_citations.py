"""Tests for human-readable source citation enrichment."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.mission_readiness_merge import (
    _format_bullet_items,
    _format_eval_crosswalk_table,
    write_compiler_brief_scaffold,
)
from src.skills.source_citations import (
    ChunkCitationIndex,
    assign_reference_numbers,
    build_source_citation,
    enrich_payload_citations,
    enrich_row_citations,
    format_chunk_scratchpad_header,
    format_ref_markers,
    format_references_section,
    humanize_document_name,
    resolve_workspace_dir_from_run_dir,
)


def test_humanize_document_name_from_pdf_path() -> None:
    label = humanize_document_name(
        file_path="Solicitation_Amendment___M6700426R00070003.pdf",
        chunk_id="doc-abc-chunk-024",
    )
    assert "Solicitation" in label
    assert "M6700426R00070003" in label


def test_build_source_citation_includes_quote_and_label() -> None:
    citation = build_source_citation(
        "chunk-abc",
        file_path="PWS_Section_C.pdf",
        content='PWS Section C.1 requires the contractor shall maintain 100% FMC.',
    )
    assert citation["chunk_id"] == "chunk-abc"
    assert "PWS Section C" in citation["section"]
    assert "100% FMC" in citation["quote"]
    assert citation["label"].startswith("PWS Section C.pdf")


def test_format_chunk_scratchpad_header_is_reader_friendly() -> None:
    header = format_chunk_scratchpad_header(
        chunk_id="doc-18757251-chunk-024",
        file_path="Solicitation_Amendment.pdf",
        content="Section M Factor 1 Management evaluates organizational structure.",
    )
    assert "Solicitation Amendment.pdf" in header
    assert "Trace id" in header
    assert "chunk-024" in header or "doc-18757251-chunk-024" in header


def test_enrich_row_citations_from_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "mcpp_rfp"
    workspace.mkdir()
    (workspace / "vdb_chunks.json").write_text(
        json.dumps(
            {
                "embedding_dim": 8,
                "data": [
                    {
                        "__id__": "chunk-test-1",
                        "file_path": "Performance_Work_Statement.pdf",
                        "content": "PWS Section C.2 COR oversight shall not exceed threshold limits.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    index = ChunkCitationIndex(workspace)
    row = enrich_row_citations(
        {
            "challenge_type": "oversight_burden",
            "source_chunk_ids": ["chunk-test-1"],
        },
        index,
    )
    assert len(row["source_citations"]) == 1
    assert "Performance Work Statement.pdf" in row["source_citations"][0]["label"]
    assert "PWS Section C.2" in row["source_citations"][0]["label"]


def test_assign_reference_numbers_dedupes_shared_chunks() -> None:
    payload = assign_reference_numbers(
        {
            "eval_crosswalk": [
                {
                    "evaluation_factor": "Factor 1",
                    "source_citations": [
                        {"chunk_id": "chunk-abc", "document": "PWS.pdf", "ref": 99},
                    ],
                }
            ],
            "customer_pain_points": [
                {
                    "challenge_type": "surge_gap",
                    "source_citations": [
                        {"chunk_id": "chunk-abc", "document": "PWS.pdf"},
                        {"chunk_id": "chunk-def", "document": "Section M.pdf"},
                    ],
                }
            ],
        }
    )
    assert payload["eval_crosswalk"][0]["source_citations"][0]["ref"] == 1
    assert payload["customer_pain_points"][0]["source_citations"][0]["ref"] == 1
    assert payload["customer_pain_points"][0]["source_citations"][1]["ref"] == 2
    assert len(payload["references"]) == 2


def test_format_ref_markers_compact() -> None:
    markers = format_ref_markers([{"ref": 1}, {"ref": 3}, {"ref": 3}])
    assert markers == "[1][3]"


def test_enrich_payload_citations_walks_arrays(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "vdb_chunks.json").write_text(
        json.dumps(
            {
                "data": [
                    {
                        "__id__": "chunk-abc",
                        "file_path": "Section_M.pdf",
                        "content": "Factor 1 Management Organizational Structure Subfactor.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    payload = {
        "eval_crosswalk": [
            {
                "evaluation_factor": "Factor 1 Management",
                "source_chunk_ids": ["chunk-abc"],
            }
        ],
        "customer_pain_points": [
            {
                "challenge_type": "surge_gap",
                "source_chunk_ids": ["chunk-abc"],
            }
        ],
    }
    enriched = enrich_payload_citations(payload, workspace)
    assert enriched["eval_crosswalk"][0]["source_citations"][0]["document"] == "Section M.pdf"
    assert enriched["eval_crosswalk"][0]["source_citations"][0]["ref"] == 1
    assert enriched["customer_pain_points"][0]["source_citations"][0]["ref"] == 1
    assert len(enriched["references"]) == 1


def test_format_eval_crosswalk_table_uses_numbered_markers() -> None:
    table = _format_eval_crosswalk_table(
        [
            {
                "evaluation_factor": "Factor 1 Management",
                "readiness_link": "Weak management degrades readiness.",
                "proof_expected": "Integrated management plan.",
                "source_citations": [{"ref": 1}, {"ref": 4}],
            }
        ]
    )
    assert "[1][4]" in table
    assert "Section M.pdf" not in table
    assert "chunk-" not in table


def test_format_bullet_items_appends_numbered_markers() -> None:
    bullets = _format_bullet_items(
        [
            {
                "challenge_type": "oversight_burden",
                "rationale": "COR over-involvement risk.",
                "source_citations": [{"ref": 2}],
            }
        ],
        fields=("challenge_type", "rationale"),
    )
    assert "[2]" in bullets
    assert "Source:" not in bullets
    assert "PWS.pdf" not in bullets
    assert "pains_handoff" not in bullets


def test_format_references_section_lists_full_sources() -> None:
    section = format_references_section(
        [
            {
                "ref": 1,
                "document": "Solicitation Amendment.pdf",
                "section": "Section M",
                "quote": "Organizational structure subfactor.",
            }
        ]
    )
    assert "## References" in section
    assert "1." in section
    assert "Solicitation Amendment.pdf" in section
    assert "Organizational structure" in section


def test_brief_scaffold_ends_with_references(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "chain_context.json").write_text(json.dumps({"role": "compiler"}), encoding="utf-8")
    merged = assign_reference_numbers(
        {
            "readiness_outcome": "Sustain FMC.",
            "eval_crosswalk": [
                {
                    "evaluation_factor": "Factor 1 Management",
                    "readiness_link": "Readiness link.",
                    "proof_expected": "Proof.",
                    "source_citations": [
                        {
                            "ref": 1,
                            "chunk_id": "chunk-abc",
                            "document": "PWS.pdf",
                            "section": "Section C.1",
                            "quote": "Maintain readiness.",
                        }
                    ],
                }
            ],
            "references": [
                {
                    "ref": 1,
                    "chunk_id": "chunk-abc",
                    "document": "PWS.pdf",
                    "section": "Section C.1",
                    "quote": "Maintain readiness.",
                }
            ],
        }
    )
    write_compiler_brief_scaffold(run_dir, merged=merged)
    brief = (artifacts / "brief.md").read_text(encoding="utf-8")
    assert brief.strip().endswith("Maintain readiness.\"")
    assert "## References" in brief
    assert "[1]" in brief
    assert "## Executive Synthesis" in brief
    assert brief.index("## Executive Synthesis") < brief.index("## References")


def test_resolve_workspace_dir_from_run_dir() -> None:
    real = Path(__file__).resolve().parents[2] / "rag_storage" / "mcpp_rfp"
    if not (real / "vdb_chunks.json").is_file():
        return
    resolved = resolve_workspace_dir_from_run_dir(
        real / "skill_runs" / "readiness-frame-pains" / "test_run"
    )
    assert resolved == real