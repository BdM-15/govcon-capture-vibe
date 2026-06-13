import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.intelligence_routes import (
    build_intel_slices,
    compute_intel,
    load_vdb,
    register_intelligence_routes,
    split_keywords,
)
from src.server.prompt_library import PromptLibraryStore


def _write_vdb(path, data) -> None:
    path.write_text(json.dumps({"data": data}), encoding="utf-8")


def test_split_keywords_accepts_lists_and_joined_strings() -> None:
    assert split_keywords(["guides", " SATISFIED_BY "]) == ["GUIDES", "SATISFIED_BY"]
    assert split_keywords("guides, satisfied_by EVIDENCES") == [
        "GUIDES",
        "SATISFIED_BY",
        "EVIDENCES",
    ]
    assert split_keywords(None) == []


def test_load_vdb_returns_empty_for_missing_or_invalid_files(tmp_path) -> None:
    assert load_vdb(tmp_path, "missing.json") == []
    (tmp_path / "bad.json").write_text("not json", encoding="utf-8")
    assert load_vdb(tmp_path, "bad.json") == []


def test_compute_intel_builds_matrices_traceability_and_gaps(tmp_path) -> None:
    _write_vdb(
        tmp_path / "vdb_entities.json",
        [
            {"entity_name": "I1", "entity_type": "proposal_instruction", "description": "instruction"},
            {"entity_name": "F1", "entity_type": "evaluation_factor", "description": "factor"},
            {"entity_name": "F2", "entity_type": "evaluation_factor", "description": "unlinked"},
            {"entity_name": "SF1", "entity_type": "subfactor", "description": "subfactor"},
            {"entity_name": "R1", "entity_type": "requirement", "description": "requirement"},
            {"entity_name": "R2", "entity_type": "requirement", "description": "missing deliverable"},
            {"entity_name": "D1", "entity_type": "deliverable", "description": "deliverable"},
            {"entity_name": "D2", "entity_type": "deliverable", "description": "unmeasured"},
            {"entity_name": "S1", "entity_type": "performance_standard", "description": "standard"},
            {"entity_name": "M1", "entity_type": "metric", "description": "metric"},
        ],
    )
    _write_vdb(
        tmp_path / "vdb_relationships.json",
        [
            {"src_id": "I1", "tgt_id": "F1", "keywords": "GUIDES"},
            {"src_id": "F1", "tgt_id": "SF1", "relationship_type": "HAS_SUBFACTOR"},
            {"src_id": "R1", "tgt_id": "D1", "keywords": ["SATISFIED_BY"]},
            {"src_id": "D1", "tgt_id": "S1", "keywords": "MEASURED_BY"},
            {"src_id": "D1", "tgt_id": "M1", "keywords": "TRACKED_BY"},
            {"src_id": "D1", "tgt_id": "F1", "keywords": "EVIDENCES"},
        ],
    )

    result = compute_intel(tmp_path, generated_at=lambda: "now")

    assert result["generated_at"] == "now"
    assert result["totals"]["entities"] == 10
    assert result["totals"]["relationships"] == 6

    instruction_row = result["lm_matrix"]["instructions"][0]
    assert instruction_row["instruction"]["id"] == "I1"
    assert instruction_row["factors"][0]["id"] == "F1"
    assert instruction_row["covered"] is True

    factor_rows = {row["factor"]["id"]: row for row in result["lm_matrix"]["factors"]}
    assert factor_rows["F1"]["covered"] is True
    assert factor_rows["F2"]["covered"] is False

    trace_rows = {row["requirement"]["id"]: row for row in result["traceability"]}
    assert trace_rows["R1"]["complete"] is True
    assert trace_rows["R1"]["deliverables"][0]["id"] == "D1"
    assert trace_rows["R2"]["complete"] is False

    coverage = {row["factor"]["id"]: row for row in result["coverage"]}
    assert coverage["F1"] == {
        "factor": {"id": "F1", "type": "evaluation_factor", "description": "factor"},
        "subfactor_count": 1,
        "instruction_count": 1,
        "evidence_count": 1,
        "score": 3,
    }

    assert [item["id"] for item in result["gaps"]["requirements_no_satisfaction"]] == ["R2"]
    assert [item["id"] for item in result["gaps"]["factors_no_instruction"]] == ["F2", "SF1"]
    assert [item["id"] for item in result["gaps"]["deliverables_no_measure"]] == ["D2"]


def test_intelligence_route_returns_computed_summary(tmp_path) -> None:
    _write_vdb(tmp_path / "vdb_entities.json", [])
    _write_vdb(tmp_path / "vdb_relationships.json", [])
    app = FastAPI()
    register_intelligence_routes(app, workspace_dir=lambda: tmp_path)
    client = TestClient(app)

    response = client.get("/api/ui/intel/summary")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["totals"] == {"entities": 0, "relationships": 0, "by_type": {}}
    assert payload["lm_matrix"] == {"instructions": [], "factors": []}


def test_build_intel_slices_includes_catalog_and_latest_runs(tmp_path) -> None:
    run_dir = tmp_path / "skill_runs" / "payment-terms-auditor" / "20260611_120000_test"
    run_dir.mkdir(parents=True)
    (run_dir / "run.md").write_text(
        "---\nrun_id: 20260611_120000_test\nskill: payment-terms-auditor\n"
        "created_at: 2026-06-11T12:00:00+00:00\nelapsed_ms: 4200\nfinish_reason: stop\n---\n",
        encoding="utf-8",
    )
    (run_dir / "response.md").write_text("Payment terms summary.", encoding="utf-8")

    store = PromptLibraryStore(workspace_dir=lambda: tmp_path)
    slices = build_intel_slices(tmp_path, prompt_library=store)
    ids = [item["id"] for item in slices]

    assert ids == [
        "overview",
        "sites",
        "evaluation",
        "mission-readiness",
        "financial",
        "logistics",
    ]
    financial = next(item for item in slices if item["id"] == "financial")
    assert financial["action"] == "skill"
    assert financial["skill"] == "payment-terms-auditor"
    assert financial["latest_run"]["run_id"] == "20260611_120000_test"

    overview = next(item for item in slices if item["id"] == "overview")
    assert overview["action"] == "chat"
    assert overview["latest_run"] is None

    mission_readiness = next(item for item in slices if item["id"] == "mission-readiness")
    assert mission_readiness["action"] == "skill"
    assert mission_readiness["skill"] == "mission-readiness-framer"
    assert mission_readiness.get("chain_preset") == "mission-readiness"
    assert "claim_gaps" in mission_readiness["skill_prompt"]
    assert mission_readiness["prompt_library_id"]
    assert mission_readiness.get("guide", {}).get("purpose")
    assert mission_readiness.get("context_tooltip")
    assert mission_readiness["related_skills"][0].get("guide", {}).get("purpose")


def test_intelligence_slices_route_returns_catalog(tmp_path) -> None:
    store = PromptLibraryStore(workspace_dir=lambda: tmp_path)
    app = FastAPI()
    register_intelligence_routes(
        app,
        workspace_dir=lambda: tmp_path,
        prompt_library=store,
    )
    client = TestClient(app)

    response = client.get("/api/ui/intel/slices")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["slices"]) == 6
    assert payload["slices"][0]["id"] == "overview"
