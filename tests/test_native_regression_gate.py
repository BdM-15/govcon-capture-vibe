from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.server.native_regression_gate import (
    build_native_ingestion_regression_report,
    write_report_json,
)


ROOT = Path(__file__).parent.parent
DOCS_PATH = ROOT / "docs" / "NATIVE_INGESTION_REGRESSION_GATE.md"


def test_fixture_gate_reports_counts_multimodal_evidence_and_known_answers() -> None:
    report = build_native_ingestion_regression_report(use_fixture=True)

    assert report["passed"] is True
    assert report["workspace"]["source"] == "fixture"
    assert report["workspace"]["entity_counts_by_type"]["requirement"] >= 1
    assert report["workspace"]["relationship_counts_by_type"]["EVALUATED_BY"] >= 1
    assert report["workspace"]["multimodal_evidence"]["tables"] >= 1
    assert report["workspace"]["known_answer_checks"][0]["passed"] is True
    assert "native_pipeline_available" in report["capabilities"]
    assert all(check["passed"] for check in report["contract_checks"])


def test_workspace_gate_reads_lightrag_artifacts_and_fails_on_missing_known_answer(tmp_path: Path) -> None:
    workspace = tmp_path / "demo"
    workspace.mkdir()
    (workspace / "vdb_entities.json").write_text(
        json.dumps(
            {
                "data": [
                    {"entity_name": "Monthly Status Report", "entity_type": "deliverable", "description": "CDRL A001"},
                    {"entity_name": "Factor 1 Technical", "entity_type": "evaluation_factor", "description": "Technical approach"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (workspace / "vdb_relationships.json").write_text(
        json.dumps(
            {
                "data": [
                    {"src_id": "Monthly Status Report", "tgt_id": "Factor 1 Technical", "keywords": "EVIDENCES"}
                ]
            }
        ),
        encoding="utf-8",
    )
    (workspace / "kv_store_text_chunks.json").write_text(
        json.dumps(
            {
                "chunk-1": {
                    "content": "[TABLE] CDRL A001 Monthly Status Report supports Factor 1 Technical Approach [/TABLE]"
                }
            }
        ),
        encoding="utf-8",
    )

    report = build_native_ingestion_regression_report(
        workspace_path=workspace,
        known_answer_checks=[
            {
                "id": "missing",
                "query": "Which clause is mandatory?",
                "expected_terms": ["52.204-21"],
            }
        ],
    )

    assert report["passed"] is False
    assert report["workspace"]["source"] == str(workspace)
    assert report["workspace"]["entity_counts_by_type"] == {
        "deliverable": 1,
        "evaluation_factor": 1,
    }
    assert report["workspace"]["relationship_counts_by_type"] == {"EVIDENCES": 1}
    assert report["workspace"]["known_answer_checks"][0]["missing_terms"] == ["52.204-21"]


def test_report_json_writer_and_cli_fixture_mode(tmp_path: Path) -> None:
    report_path = tmp_path / "gate-report.json"
    report = build_native_ingestion_regression_report(use_fixture=True)
    write_report_json(report, report_path)

    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["passed"] is True

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "native_ingestion_regression_gate.py"),
            "--fixture",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    cli_report = json.loads(completed.stdout)
    assert cli_report["passed"] is True
    assert cli_report["workspace"]["source"] == "fixture"


def test_native_ingestion_regression_gate_is_documented_for_agents() -> None:
    source = DOCS_PATH.read_text(encoding="utf-8")

    assert "tools/native_ingestion_regression_gate.py --fixture --json" in source
    assert "--workspace rag_storage/<workspace>" in source
    assert "known-answer" in source
    assert "MinerU" in source
    assert "VLM" in source
    assert ".github/copilot-instructions.md" in source