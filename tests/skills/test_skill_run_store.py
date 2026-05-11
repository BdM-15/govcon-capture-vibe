import json
from datetime import datetime, timezone
from pathlib import Path

from src.skills.runs import SkillRunStore


def test_persist_legacy_run_round_trips_and_deletes(tmp_path: Path) -> None:
    store = SkillRunStore()
    started = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    run_id, run_dir = store.persist_legacy_run(
        workspace_root=tmp_path,
        skill_name="proposal-generator",
        workspace="demo-ws",
        user_prompt="Draft XYZ!",
        composed_prompt="full prompt",
        response="final response",
        entities_used=["requirement", "evaluation_factor"],
        warnings=["careful"],
        elapsed_ms=123,
        started_at=started,
    )

    assert run_id == "20260102_030405_draft_xyz"
    assert Path(run_dir).is_dir()

    listed = store.list_runs(tmp_path, skill_name="proposal-generator")
    assert listed[0]["run_id"] == run_id
    assert listed[0]["workspace"] == "demo-ws"
    assert listed[0]["entities_used"] == ["requirement", "evaluation_factor"]

    detail = store.get_run(tmp_path, "proposal-generator", run_id)
    assert detail is not None
    assert detail["response"] == "final response"
    assert detail["prompt"] == "full prompt"
    assert detail["artifacts"] == []
    assert detail["transcript"] == []
    assert detail["tool_outputs"] == []

    assert store.delete_run(tmp_path, "proposal-generator", run_id) is True
    assert store.get_run(tmp_path, "proposal-generator", run_id) is None


def test_tools_run_detail_includes_transcript_artifacts_and_tool_outputs(
    tmp_path: Path,
) -> None:
    store = SkillRunStore()
    started = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    run_id, run_dir = store.create_run_dir(
        workspace_root=tmp_path,
        skill_name="compliance-auditor",
        user_prompt="Audit clauses",
        started_at=started,
        create_tool_outputs=True,
    )
    (run_dir / "transcript.json").write_text(
        json.dumps([{"kind": "assistant", "content": "checking"}]),
        encoding="utf-8",
    )
    (run_dir / "artifacts" / "matrix.xlsx").write_bytes(b"xlsx")
    (run_dir / "tool_outputs" / "001.stdout.txt").write_text("ok", encoding="utf-8")

    store.persist_tools_run(
        run_dir=run_dir,
        run_id=run_id,
        skill_name="compliance-auditor",
        workspace="demo-ws",
        user_prompt="Audit clauses",
        response="done",
        turns=2,
        tool_calls=3,
        finish_reason="stop",
        usage_total={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        warnings=[],
        elapsed_ms=456,
        started_at=started,
    )

    detail = store.get_run(tmp_path, "compliance-auditor", run_id)
    assert detail is not None
    assert detail["metadata"]["runtime"] == "tools"
    assert detail["response"] == "done"
    assert detail["transcript"] == [{"kind": "assistant", "content": "checking"}]
    assert detail["artifacts"] == [
        {
            "name": "matrix.xlsx",
            "size": "4",
            "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "display_name": "Matrix",
            "products": ["compliance_findings", "gap_list"],
        }
    ]
    assert detail["tool_outputs"] == [{"name": "001.stdout.txt", "size": "2"}]


def test_project_run_payload_marks_interrupted_run_as_resumeable(tmp_path: Path) -> None:
    store = SkillRunStore()
    started = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    run_id, _run_dir = store.persist_legacy_run(
        workspace_root=tmp_path,
        skill_name="huashu-design",
        workspace="demo-ws",
        user_prompt="Build briefing deck",
        composed_prompt="full prompt",
        response=(
            "**GAP IDENTIFIED - Cannot fully satisfy quality gate.**\n\n"
            "**Exact gaps (per quality gate):**\n"
            "- Choose design direction\n"
            "- Confirm output format\n"
        ),
        entities_used=[],
        warnings=[],
        elapsed_ms=123,
        started_at=started,
    )

    detail = store.get_run(tmp_path, "huashu-design", run_id)
    assert detail is not None

    projected = store.project_run_payload(detail)

    assert projected["metadata"]["user_prompt"] == "Build briefing deck"
    assert projected["status"] == "interrupted"
    assert projected["can_resume"] is True
    assert projected["input_request"] == {
        "needed": True,
        "kind": "missing_input",
        "title": "Missing Input",
        "skill": "huashu-design",
        "missing_inputs": [
            "Choose design direction",
            "Confirm output format",
        ],
    }


def test_project_run_payload_marks_question_run_as_resumeable(tmp_path: Path) -> None:
    store = SkillRunStore()
    started = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    run_id, _run_dir = store.persist_legacy_run(
        workspace_root=tmp_path,
        skill_name="grill-me",
        workspace="demo-ws",
        user_prompt="Grill me on AFCAP VI",
        composed_prompt="full prompt",
        response=(
            "**Detected Mode: Bid Strategy**\n\n"
            "**Q1: What's your estimated Pwin threshold for pursuing AFCAP VI, and what specific evidence sets that number?**\n"
            "*Recommended: 40-50% minimum per standard Bid/No-Bid frameworks.*\n"
        ),
        entities_used=[],
        warnings=[],
        elapsed_ms=123,
        started_at=started,
    )

    listed = store.list_runs(tmp_path, skill_name="grill-me")
    assert listed[0]["run_id"] == run_id
    assert listed[0]["status"] == "interrupted"
    assert listed[0]["can_resume"] is True

    detail = store.get_run(tmp_path, "grill-me", run_id)
    assert detail is not None

    projected = store.project_run_payload(detail)

    assert projected["status"] == "interrupted"
    assert projected["can_resume"] is True
    assert projected["missing_inputs"] == [
        "What's your estimated Pwin threshold for pursuing AFCAP VI, and what specific evidence sets that number?"
    ]
    assert projected["input_request"] == {
        "needed": True,
        "kind": "question",
        "title": "Question",
        "skill": "grill-me",
        "prompt": "What's your estimated Pwin threshold for pursuing AFCAP VI, and what specific evidence sets that number?",
        "missing_inputs": [
            "What's your estimated Pwin threshold for pursuing AFCAP VI, and what specific evidence sets that number?"
        ],
    }


def test_project_run_payload_marks_long_question_run_as_resumeable(
    tmp_path: Path,
) -> None:
    store = SkillRunStore()
    started = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    run_id, _run_dir = store.persist_legacy_run(
        workspace_root=tmp_path,
        skill_name="grill-me",
        workspace="demo-ws",
        user_prompt="Grill me on AFCAP VI",
        composed_prompt="full prompt",
        response=(
            "**Which area should I stress-test for your AFCAP VI pursuit - Bid Strategy (Pursuit Decision Phase gate, Pwin assessment), Capture Plan (customer engagement, teaming, Black Hat), Proposal Approach (technical scenario response per Subfactor 1 [doc-d476d6ecf16e6cd2b3a76545f5d2a3d7-chunk-000], program management plans per L.3.3 Subfactor 2 [doc-1dd044e7c06a80c3590c3781850f25af-chunk-000]), or Pricing (FFP/CPIF task orders per H001 [doc-455de3cb2b36b30f23fd10100248faec-chunk-000])?**\n\n"
            "*Recommended: Bid Strategy - AFCAP VI is an IDIQ with multiple awards and a technically acceptable gate.*\n"
        ),
        entities_used=[],
        warnings=[],
        elapsed_ms=123,
        started_at=started,
    )

    listed = store.list_runs(tmp_path, skill_name="grill-me")
    assert listed[0]["run_id"] == run_id
    assert listed[0]["status"] == "interrupted"
    assert listed[0]["can_resume"] is True

    detail = store.get_run(tmp_path, "grill-me", run_id)
    assert detail is not None

    projected = store.project_run_payload(detail)

    expected_question = (
        "Which area should I stress-test for your AFCAP VI pursuit - Bid Strategy (Pursuit Decision Phase gate, Pwin assessment), Capture Plan (customer engagement, teaming, Black Hat), Proposal Approach (technical scenario response per Subfactor 1 [doc-d476d6ecf16e6cd2b3a76545f5d2a3d7-chunk-000], program management plans per L.3.3 Subfactor 2 [doc-1dd044e7c06a80c3590c3781850f25af-chunk-000]), or Pricing (FFP/CPIF task orders per H001 [doc-455de3cb2b36b30f23fd10100248faec-chunk-000])?"
    )
    assert projected["status"] == "interrupted"
    assert projected["can_resume"] is True
    assert projected["missing_inputs"] == [expected_question]
    assert projected["input_request"] == {
        "needed": True,
        "kind": "question",
        "title": "Question",
        "skill": "grill-me",
        "prompt": expected_question,
        "missing_inputs": [expected_question],
    }


def test_get_artifact_path_rejects_unsafe_inputs(tmp_path: Path) -> None:
    store = SkillRunStore()
    started = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    run_id, run_dir = store.create_run_dir(
        workspace_root=tmp_path,
        skill_name="renderers",
        user_prompt="Render",
        started_at=started,
    )
    artifact = run_dir / "artifacts" / "brief.md"
    artifact.write_text("# Brief", encoding="utf-8")

    assert store.get_artifact_path(tmp_path, "renderers", run_id, "brief.md") == artifact
    assert store.get_artifact_path(tmp_path, "renderers", "bad", "brief.md") is None
    assert store.get_artifact_path(tmp_path, "renderers", run_id, "../brief.md") is None
    assert store.get_artifact_path(tmp_path, "renderers", run_id, "missing.md") is None
