"""Contract tests for fragmented Capture Workbench UI (#190)."""

from __future__ import annotations

from pathlib import Path

from src.ui.workbench_assembler import (
    WORKBENCH_VIEW_IDS,
    assemble_workbench_html,
    view_fragment_path,
)

_STATIC = Path(__file__).resolve().parents[2] / "src" / "ui" / "static"


def test_workbench_shell_is_slimmer_than_legacy_monolith() -> None:
    shell_lines = len((_STATIC / "index.shell.html").read_text(encoding="utf-8").splitlines())
    assert shell_lines < 2500, f"shell still bloated at {shell_lines} lines"


def test_all_view_fragments_exist_on_disk() -> None:
    for view_id in WORKBENCH_VIEW_IDS:
        assert view_fragment_path(_STATIC, view_id).is_file(), view_id


def test_assembler_stitches_every_nav_view() -> None:
    html = assemble_workbench_html(str(_STATIC))
    for view_id in WORKBENCH_VIEW_IDS:
        assert f"active === '{view_id}'" in html, f"assembled HTML missing {view_id} section"


def test_assembled_html_preserves_studio_preview_contract() -> None:
    html = assemble_workbench_html(str(_STATIC))
    assert 'class="studio-filename-btn text-neon-cyan"' in html
    assert '@click="openStudioPreview(row.deliverable)"' in html
    assert "Version History" in html


def test_assembled_html_preserves_skill_resume_panel_template() -> None:
    html = assemble_workbench_html(str(_STATIC))
    assert 'id="skill-run-input-request-panel-template"' in html
    assert 'id="chain-input-request-panel-template"' in html