from datetime import datetime, timezone

from src.skills.runs import (
    SkillRunStore,
    build_legacy_run_envelope,
    build_tools_run_envelope,
    list_deliverables_under_base,
    list_runs_under_base,
)


def test_build_run_envelopes_include_expected_headers() -> None:
    started = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    legacy = build_legacy_run_envelope(
        run_id="20260102_030405_demo",
        skill_name="proposal-generator",
        workspace="ws-a",
        user_prompt="Draft volume",
        response="done",
        entities_used=["requirement"],
        warnings=["careful"],
        elapsed_ms=12,
        started_at=started,
    )
    tools = build_tools_run_envelope(
        run_id="20260102_030405_demo",
        skill_name="proposal-generator",
        workspace="ws-a",
        user_prompt="Draft volume",
        response="done",
        turns=2,
        tool_calls=3,
        finish_reason="stop",
        usage_total={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        warnings=[],
        elapsed_ms=12,
        started_at=started,
    )

    assert "# Skill Run" in legacy
    assert "entities_used: [requirement]" in legacy
    assert "# Skill Run (tools mode)" in tools
    assert "tool_calls: 3" in tools
    assert "response.md" in tools


def test_list_runs_under_base_and_deliverables_under_base(tmp_path) -> None:
    base = tmp_path / "skill_runs"
    run_dir = base / "proposal-generator" / "20260102_030405_demo"
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "run.md").write_text(
        "---\n"
        "run_id: 20260102_030405_demo\n"
        "skill: proposal-generator\n"
        "workspace: ws-a\n"
        "created_at: 2026-01-02T03:04:05+00:00\n"
        "elapsed_ms: 12\n"
        "entities_used: [requirement]\n"
        "response_chars: 4\n"
        "---\n\n"
        "# Skill Run\n",
        encoding="utf-8",
    )
    (run_dir / "response.md").write_text("done", encoding="utf-8")
    (run_dir / "artifacts" / "draft.docx").write_bytes(b"x")
    rogue = base / "proposal-generator" / "bad"
    (rogue / "artifacts").mkdir(parents=True)
    (rogue / "run.md").write_text("---\n---\n", encoding="utf-8")
    (rogue / "artifacts" / "leak.txt").write_bytes(b"x")

    runs = list_runs_under_base(base, skill_name="proposal-generator")
    deliverables = list_deliverables_under_base(
        base,
        is_safe_run_id=lambda run_id: run_id.startswith("2026"),
    )

    assert runs[0]["run_id"] == "20260102_030405_demo"
    assert runs[0]["response_chars"] == 4
    assert deliverables == [
        {
            "skill": "proposal-generator",
            "run_id": "20260102_030405_demo",
            "filename": "draft.docx",
            "display_name": "Draft",
            "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size": 1,
            "created_at": "2026-01-02T03:04:05+00:00",
            "title": None,
            "ext": "docx",
        }
    ]


def test_skill_run_store_can_trash_and_restore_runs(tmp_path) -> None:
    workspace_root = tmp_path
    store = SkillRunStore()
    run_dir = workspace_root / "skill_runs" / "proposal-generator" / "20260102_030405_demo"
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "run.md").write_text(
        "---\n"
        "run_id: 20260102_030405_demo\n"
        "skill: proposal-generator\n"
        "workspace: ws-a\n"
        "created_at: 2026-01-02T03:04:05+00:00\n"
        "elapsed_ms: 12\n"
        "prompt_preview: Draft volume\n"
        "response_chars: 4\n"
        "---\n\n"
        "# Skill Run\n",
        encoding="utf-8",
    )
    (run_dir / "response.md").write_text("done", encoding="utf-8")
    (run_dir / "artifacts" / "draft.docx").write_bytes(b"x")

    trashed = store.trash_run(workspace_root, "proposal-generator", "20260102_030405_demo")

    assert trashed is not None
    assert trashed["run_id"] == "20260102_030405_demo"
    assert trashed["artifact_count"] == 1
    assert not run_dir.exists()
    assert store.list_runs(workspace_root, skill_name="proposal-generator") == []
    trashed_runs = store.list_trashed_runs(workspace_root, skill_name="proposal-generator")
    assert len(trashed_runs) == 1
    assert trashed_runs[0]["trash_id"] == trashed["trash_id"]

    restored = store.restore_trashed_runs(workspace_root, [trashed["trash_id"]])

    assert len(restored["restored"]) == 1
    assert run_dir.exists()
    runs = store.list_runs(workspace_root, skill_name="proposal-generator")
    assert runs[0]["run_id"] == "20260102_030405_demo"