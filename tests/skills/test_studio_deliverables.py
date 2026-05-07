"""Phase 6a — unit tests for the Studio deliverables index.

Covers ``SkillManager.list_deliverables`` (the cross-skill artifact
flattener) at the disk-walking layer. The HTTP route in
``src/server/ui_routes.py`` is a thin ``asyncio.to_thread`` wrapper, so
exercising the manager method gives full coverage of the indexing logic
without spinning up FastAPI + a workspace.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.skills.manager import SkillManager


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
        artifacts={"brief.md": b"# brief", "brief.html": b"<h1>brief</h1>"},
        created_at="2025-04-28T13:00:00",
    )

    rows = mgr.list_deliverables(tmp_path)
    assert len(rows) == 3

    # Newest-first ordering by created_at.
    assert rows[0]["filename"] == "brief.html"
    assert rows[0]["display_name"] == "Brief"
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


def test_list_deliverables_hides_source_artifacts(tmp_path: Path) -> None:
    mgr = SkillManager()
    _seed_run(
        tmp_path,
        skill="competitive-intel",
        run_id="20250428_130000_second",
        artifacts={
            "report.md": b"# source",
            "report.json": b"{}",
            "final.html": b"<h1>final</h1>",
        },
    )

    rows = mgr.list_deliverables(tmp_path)

    assert [row["filename"] for row in rows] == ["final.html"]


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
