"""Phase 6a — unit tests for the Studio deliverables index.

Covers ``SkillManager.list_deliverables`` (the cross-skill artifact
flattener) at the disk-walking layer. The HTTP route in
``src/server/ui_routes.py`` is a thin ``asyncio.to_thread`` wrapper, so
exercising the manager method gives full coverage of the indexing logic
without spinning up FastAPI + a workspace.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.skills.manager import SkillManager
from src.skills.runs import SkillRunStore


def _seed_run(
    workspace_root: Path,
    *,
    skill: str,
    run_id: str,
    artifacts: dict[str, bytes],
    created_at: str = "2025-04-28T12:00:00",
) -> Path:
    """Create a fake skill_runs/<skill>/<run_id>/ tree on disk."""
    run_dir = workspace_root / "skill_runs" / skill / run_id
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "run.md").write_text(
        f"---\nrun_id: {run_id}\nskill: {skill}\nworkspace: ws\n"
        f"created_at: {created_at}\nelapsed_ms: 1000\n"
        f"entities_used: []\nresponse_chars: 100\n---\n\n# Skill Run\n",
        encoding="utf-8",
    )
    (run_dir / "response.md").write_text("ok", encoding="utf-8")
    for name, data in artifacts.items():
        (run_dir / "artifacts" / name).write_bytes(data)
    return run_dir


def test_list_deliverables_empty_when_no_runs(tmp_path: Path) -> None:
    mgr = SkillManager()
    assert mgr.list_deliverables(tmp_path) == []


def test_list_deliverables_flattens_across_skills(tmp_path: Path) -> None:
    mgr = SkillManager()
    _seed_run(
        tmp_path,
        skill="proposal-generator",
        run_id="20250428_120000_first",
        artifacts={"draft.docx": b"docx-bytes", "compliance.xlsx": b"xlsx-bytes"},
        created_at="2025-04-28T12:00:00",
    )
    _seed_run(
        tmp_path,
        skill="competitive-intel",
        run_id="20250428_130000_second",
        artifacts={
            "brief.md": b"# MCPP Competitive Intel Brief\n",
            "brief.html": b"<h1>MCPP Brief</h1>",
        },
        created_at="2025-04-28T13:00:00",
    )

    rows = mgr.list_deliverables(tmp_path)
    assert len(rows) == 3

    # Newest-first ordering by created_at.
    assert rows[0]["filename"] == "brief.html"
    assert rows[0]["display_name"] == "MCPP Brief"
    assert rows[0]["run_label"] == "28 Apr 13:00 · second"
    assert rows[0]["skill"] == "competitive-intel"
    assert rows[0]["created_at"] == "2025-04-28T13:00:00"

    # Subsequent rows from the older run.
    older_filenames = {r["filename"] for r in rows[1:]}
    assert older_filenames == {"draft.docx", "compliance.xlsx"}
    for row in rows[1:]:
        assert row["skill"] == "proposal-generator"
        assert row["run_id"] == "20250428_120000_first"


def test_list_deliverables_prefers_manifest_display_name(tmp_path: Path) -> None:
    mgr = SkillManager()
    run_dir = _seed_run(
        tmp_path,
        skill="competitive-intel",
        run_id="20250428_130000_second",
        artifacts={"competitive_intel_obligation.json": b"{}", "burn.html": b"html"},
        created_at="2025-04-28T13:00:00",
    )
    (run_dir / "artifacts_manifest.json").write_text(
        '{\n  "burn.html": {\n    "display_name": "AFCAP V Parent Vehicle Burn Intel"\n  }\n}\n',
        encoding="utf-8",
    )

    rows = mgr.list_deliverables(tmp_path)

    assert rows[0]["filename"] == "burn.html"
    assert rows[0]["display_name"] == "AFCAP V Parent Vehicle Burn Intel"


def test_list_deliverables_exposes_manifest_or_contract_products(tmp_path: Path) -> None:
    mgr = SkillManager()
    run_dir = _seed_run(
        tmp_path,
        skill="competitive-intel",
        run_id="20250428_130000_second",
        artifacts={"burn.html": b"html", "orders.xlsx": b"xlsx"},
        created_at="2025-04-28T13:00:00",
    )
    (run_dir / "artifacts_manifest.json").write_text(
        json.dumps({"orders.xlsx": {"products": ["obligation_data"]}}),
        encoding="utf-8",
    )

    rows = {row["filename"]: row for row in mgr.list_deliverables(tmp_path)}

    assert rows["orders.xlsx"]["products"] == ["obligation_data"]
    assert "award_history" in rows["burn.html"]["products"]


def test_run_store_annotates_artifact_manifest_products(tmp_path: Path) -> None:
    store = SkillRunStore()
    run_dir = _seed_run(
        tmp_path,
        skill="price-to-win",
        run_id="20250428_130000_second",
        artifacts={"ptw.xlsx": b"xlsx"},
    )

    changed = store.annotate_artifact_products(
        tmp_path,
        "price-to-win",
        "20250428_130000_second",
    )

    assert changed == 1
    manifest = json.loads((run_dir / "artifacts_manifest.json").read_text(encoding="utf-8"))
    assert "pricing_stack" in manifest["ptw.xlsx"]["products"]


def test_list_deliverables_attaches_chain_trace(tmp_path: Path) -> None:
    mgr = SkillManager()
    _seed_run(
        tmp_path,
        skill="price-to-win",
        run_id="20260507_120000_ptw",
        artifacts={"ptw.xlsx": b"workbook"},
        created_at="2026-05-07T12:00:00",
    )
    chain_id = "20260507_121500_intel_to_ptw"
    chain_dir = tmp_path / "skill_chains" / chain_id
    chain_dir.mkdir(parents=True)
    (chain_dir / "chain.json").write_text(
        json.dumps(
            {
                "chain_id": chain_id,
                "workspace": "ws",
                "status": "completed",
                "mode": "original",
                "spec": {
                    "name": "intel-to-ptw",
                    "steps": [
                        {"id": "intel", "skill": "competitive-intel"},
                        {"id": "ptw", "skill": "price-to-win"},
                    ],
                },
                "steps": {
                    "ptw": {
                        "id": "ptw",
                        "skill": "price-to-win",
                        "run_id": "20260507_120000_ptw",
                        "status": "completed",
                        "artifacts": [{"name": "ptw.xlsx"}],
                    }
                },
                "created_at": "2026-05-07T12:15:00",
            }
        ),
        encoding="utf-8",
    )

    rows = mgr.list_deliverables(tmp_path)

    assert rows[0]["chain"]["chain_id"] == chain_id
    assert rows[0]["chain"]["name"] == "intel-to-ptw"
    assert rows[0]["chain"]["step_id"] == "ptw"
    assert rows[0]["chain"]["step_count"] == 2
    assert rows[0]["chain"]["can_resume"] is False


def test_project_chain_payload_exposes_resume_fields_for_detail_views(tmp_path: Path) -> None:
    store = SkillRunStore()
    chain_id = "20260507_121500_detail_projection"
    chain_dir = tmp_path / "skill_chains" / chain_id
    chain_dir.mkdir(parents=True)
    (chain_dir / "chain.json").write_text(
        json.dumps(
            {
                "chain_id": chain_id,
                "workspace": "ws",
                "status": "failed",
                "mode": "original",
                "input_request": {
                    "needed": True,
                    "step_id": "ptw",
                    "skill": "price-to-win",
                    "missing_inputs": ["Missing incumbent PIID"],
                    "resume_step_id": "ptw",
                },
                "spec": {
                    "name": "detail-projection",
                    "steps": [
                        {"id": "intel", "skill": "competitive-intel"},
                        {"id": "ptw", "skill": "price-to-win", "depends_on": ["intel"]},
                    ],
                },
                "steps": {
                    "intel": {
                        "id": "intel",
                        "skill": "competitive-intel",
                        "status": "completed",
                    },
                    "ptw": {
                        "id": "ptw",
                        "skill": "price-to-win",
                        "status": "failed",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    payload = store.get_chain_run(tmp_path, chain_id)
    assert payload is not None

    projected = store.project_chain_payload(payload)

    assert projected["resume_step_id"] == "ptw"
    assert projected["can_resume"] is True
    assert projected["step_count"] == 2


def test_list_deliverables_marks_failed_chain_as_resumeable(tmp_path: Path) -> None:
    mgr = SkillManager()
    _seed_run(
        tmp_path,
        skill="renderers",
        run_id="20260507_120000_render",
        artifacts={"brief.docx": b"docx"},
        created_at="2026-05-07T12:00:00",
    )
    chain_id = "20260507_121500_ui_resume_artifact"
    chain_dir = tmp_path / "skill_chains" / chain_id
    chain_dir.mkdir(parents=True)
    (chain_dir / "chain.json").write_text(
        json.dumps(
            {
                "chain_id": chain_id,
                "workspace": "ws",
                "status": "failed",
                "mode": "original",
                "spec": {
                    "name": "ui-resume-artifact",
                    "steps": [
                        {"id": "renderers", "skill": "renderers"},
                        {
                            "id": "postcheck",
                            "skill": "proposal-generator",
                            "depends_on": ["renderers"],
                        },
                    ],
                },
                "steps": {
                    "renderers": {
                        "id": "renderers",
                        "skill": "renderers",
                        "run_id": "20260507_120000_render",
                        "status": "completed",
                        "artifacts": [{"name": "brief.docx"}],
                    },
                    "postcheck": {
                        "id": "postcheck",
                        "skill": "proposal-generator",
                        "status": "failed",
                        "error": "synthetic postcheck failure",
                    },
                },
                "created_at": "2026-05-07T12:15:00",
                "updated_at": "2026-05-07T12:20:00",
                "finished_at": "2026-05-07T12:20:00",
                "error": "synthetic postcheck failure",
            }
        ),
        encoding="utf-8",
    )

    rows = mgr.list_deliverables(tmp_path)

    assert rows[0]["chain"]["chain_id"] == chain_id
    assert rows[0]["chain"]["status"] == "failed"
    assert rows[0]["chain"]["can_resume"] is True
    assert rows[0]["chain"]["resume_step_id"] == "postcheck"


def test_list_deliverables_hides_source_chain_artifacts_and_keeps_promoted_outputs(
    tmp_path: Path,
) -> None:
    mgr = SkillManager()
    _seed_run(
        tmp_path,
        skill="competitive-intel",
        run_id="20260507_120000_intel",
        artifacts={"competitive_intel_brief.docx": b"docx"},
        created_at="2026-05-07T12:00:00",
    )
    _seed_run(
        tmp_path,
        skill="renderers",
        run_id="20260507_121000_render",
        artifacts={"final_brief.docx": b"docx"},
        created_at="2026-05-07T12:10:00",
    )
    chain_id = "20260507_121500_promoted_outputs"
    chain_dir = tmp_path / "skill_chains" / chain_id
    chain_dir.mkdir(parents=True)
    (chain_dir / "chain.json").write_text(
        json.dumps(
            {
                "chain_id": chain_id,
                "workspace": "ws",
                "status": "partial",
                "mode": "original",
                "spec": {
                    "name": "promoted-outputs",
                    "steps": [
                        {"id": "intel", "skill": "competitive-intel"},
                        {
                            "id": "render",
                            "skill": "renderers",
                            "depends_on": ["intel"],
                        },
                    ],
                },
                "promoted_artifacts": [
                    {
                        "step_id": "render",
                        "skill": "renderers",
                        "run_id": "20260507_121000_render",
                        "filename": "final_brief.docx",
                    }
                ],
                "steps": {
                    "intel": {
                        "id": "intel",
                        "skill": "competitive-intel",
                        "run_id": "20260507_120000_intel",
                        "status": "partial",
                        "artifacts": [{"name": "competitive_intel_brief.docx"}],
                    },
                    "render": {
                        "id": "render",
                        "skill": "renderers",
                        "run_id": "20260507_121000_render",
                        "status": "partial",
                        "artifacts": [{"name": "final_brief.docx"}],
                    },
                },
                "created_at": "2026-05-07T12:15:00",
            }
        ),
        encoding="utf-8",
    )

    rows = mgr.list_deliverables(tmp_path)

    assert [row["filename"] for row in rows] == ["final_brief.docx"]
    assert rows[0]["run_kind"] == "chain"
    assert rows[0]["surface"] == "promoted"
    assert rows[0]["chain"]["status"] == "partial"


def test_list_deliverables_hides_source_artifacts(tmp_path: Path) -> None:
    mgr = SkillManager()
    _seed_run(
        tmp_path,
        skill="competitive-intel",
        run_id="20250428_130000_second",
        artifacts={
            "report.md": b"# source",
            "report.json": b"{}",
            "final.docx": b"docx",
        },
    )

    rows = mgr.list_deliverables(tmp_path)

    assert [row["filename"] for row in rows] == ["final.docx"]


def test_list_deliverables_resolves_office_mimes(tmp_path: Path) -> None:
    mgr = SkillManager()
    _seed_run(
        tmp_path,
        skill="proposal-generator",
        run_id="20250428_120000_run",
        artifacts={
            "x.docx": b"x",
            "y.xlsx": b"y",
            "z.pptx": b"z",
            "w.pdf": b"w",
            "n.html": b"n",
        },
    )
    by_name = {r["filename"]: r for r in mgr.list_deliverables(tmp_path)}
    assert (
        by_name["x.docx"]["mime"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert (
        by_name["y.xlsx"]["mime"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert (
        by_name["z.pptx"]["mime"]
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert by_name["w.pdf"]["mime"] == "application/pdf"
    assert by_name["n.html"]["mime"] == "text/html"
    # Extension is normalized lowercase, no leading dot.
    assert by_name["x.docx"]["ext"] == "docx"


def test_list_deliverables_skips_unsafe_run_ids(tmp_path: Path) -> None:
    mgr = SkillManager()
    bad_run_dir = tmp_path / "skill_runs" / "proposal-generator" / "../escape"
    # Cannot actually create the literal "../escape" — instead simulate a
    # rogue run dir whose name doesn't match the safe pattern.
    rogue = tmp_path / "skill_runs" / "proposal-generator" / "not_a_run_id"
    (rogue / "artifacts").mkdir(parents=True)
    (rogue / "artifacts" / "leak.txt").write_bytes(b"x")
    (rogue / "run.md").write_text("---\n---\n", encoding="utf-8")

    assert mgr.list_deliverables(tmp_path) == []


def test_list_deliverables_ignores_runs_without_artifacts_dir(tmp_path: Path) -> None:
    mgr = SkillManager()
    run_dir = tmp_path / "skill_runs" / "proposal-generator" / "20250428_120000_x"
    run_dir.mkdir(parents=True)
    (run_dir / "run.md").write_text(
        "---\nrun_id: 20250428_120000_x\nskill: proposal-generator\n"
        "workspace: ws\ncreated_at: 2025-04-28T12:00:00\nelapsed_ms: 1\n"
        "entities_used: []\nresponse_chars: 0\n---\n",
        encoding="utf-8",
    )
    assert mgr.list_deliverables(tmp_path) == []


def test_list_deliverables_disambiguates_colliding_titles_with_prompt_variants(
    tmp_path: Path,
) -> None:
    mgr = SkillManager()
    shared_brief = "# Mission Readiness Frame — MCPP RFP (M67004-26-R-0007)\n".encode(
        "utf-8"
    )
    run_a = _seed_run(
        tmp_path,
        skill="mission-readiness-framer",
        run_id="20260611_151031_frame_v1",
        artifacts={"mission_readiness_frame_brief.docx": b"docx-a"},
        created_at="2026-06-11T15:10:31",
    )
    run_b = _seed_run(
        tmp_path,
        skill="mission-readiness-framer",
        run_id="20260611_161045_frame_v2",
        artifacts={"mission_readiness_frame_brief.docx": b"docx-b"},
        created_at="2026-06-11T16:10:45",
    )
    (run_a / "artifacts" / "brief.md").write_bytes(shared_brief)
    (run_b / "artifacts" / "brief.md").write_bytes(shared_brief)
    (run_a / "run.md").write_text(
        (run_a / "run.md").read_text(encoding="utf-8")
        + "\n## User Prompt\n\nBuild frame with OCI transition emphasis for MCPP.\n",
        encoding="utf-8",
    )
    (run_b / "run.md").write_text(
        (run_b / "run.md").read_text(encoding="utf-8")
        + "\n## User Prompt\n\nRebuild frame focusing on logistics SLA and staffing risks.\n",
        encoding="utf-8",
    )

    rows = {
        row["run_id"]: row["display_name"]
        for row in mgr.list_deliverables(tmp_path)
        if row["skill"] == "mission-readiness-framer"
    }

    assert rows["20260611_151031_frame_v1"] == (
        "MCPP RFP (M67004-26-R-0007) · frame with OCI transition emphasis for MCPP · Brief"
    )
    assert rows["20260611_161045_frame_v2"] == (
        "MCPP RFP (M67004-26-R-0007) · frame focusing on logistics SLA and staffing · Brief"
    )


def test_list_deliverables_respects_limit(tmp_path: Path) -> None:
    mgr = SkillManager()
    artifacts = {f"a{i}.pdf": b"x" for i in range(10)}
    _seed_run(
        tmp_path,
        skill="proposal-generator",
        run_id="20250428_120000_x",
        artifacts=artifacts,
    )
    rows = mgr.list_deliverables(tmp_path, limit=3)
    assert len(rows) == 3
