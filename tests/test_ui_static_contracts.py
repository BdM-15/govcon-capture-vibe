from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).parent.parent
_INDEX_HTML = _ROOT / "src" / "ui" / "static" / "index.html"
_UI_STATIC_ROOT = _ROOT / "src" / "ui" / "static"
_PREVIEW_HELPERS = _ROOT / "src" / "ui" / "static" / "app" / "theseus-preview-helpers.js"
_BANNED_MOJIBAKE = (
    "Î",
    "Â",
    "â€",
    "â†",
    "â€™",
    "â€œ",
    "â€\"",
    "â€¢",
    "âš ",
)


def test_delete_modal_storage_display_uses_null_safe_guard() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")

    assert (
        "deleteModal.target?.storage_mb != null ? deleteModal.target.storage_mb + ' MB' : 'not present'"
        in source
    ), "Delete modal storage display must guard null/undefined targets before reading storage_mb."


def test_ui_static_files_do_not_contain_common_mojibake_sequences() -> None:
    offenders: list[str] = []

    for path in _UI_STATIC_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".html", ".js", ".css", ".svg"}:
            continue
        content = path.read_text(encoding="utf-8")
        bad = [token for token in _BANNED_MOJIBAKE if token in content]
        if bad:
            offenders.append(f"{path.relative_to(_ROOT)}: {', '.join(sorted(set(bad)))}")

    assert not offenders, "UI mojibake detected:\n" + "\n".join(offenders)


def test_studio_filename_button_is_only_preview_trigger() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")
    start = source.index('class="studio-filename-btn text-neon-cyan"')
    end = source.index("</button>", start)
    filename_button = source[start:end]

    assert '@click="openStudioPreview(row.deliverable)"' in filename_button
    assert 'x-text="d.filename"' not in filename_button
    assert 'title="Preview inline"' not in source


def test_studio_preview_header_hides_raw_filename_subline() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")
    start = source.index('x-text="studioPreview.deliverable && (studioPreview.deliverable.display_name || studioPreview.deliverable.filename)"')
    end = source.index('x-show="studioPreview.deliverable"', start)
    header_slice = source[start:end]

    assert 'x-show="studioPreview.deliverable && studioPreview.deliverable.display_name && studioPreview.deliverable.display_name !== studioPreview.deliverable.filename"' not in header_slice


def test_studio_preview_keeps_reasoning_link_without_provenance_rail() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")

    assert "Full reasoning" in source
    assert '<aside class="studio-provenance-rail">' not in source
    assert "Run Artifacts" not in source
    assert "Transcript Steps" not in source
    assert 'x-show="studioPreview.provenanceLoading"' not in source
    assert 'x-for="artifact in studioPreviewArtifacts()"' not in source


def test_studio_preview_exposes_version_history_and_compare() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")
    helpers = _PREVIEW_HELPERS.read_text(encoding="utf-8")

    assert "Version History" in source
    assert "Version diff" in source
    assert "Compare" in source
    assert "Current version" in helpers
    assert "Older version" in helpers
    assert "Diff ready" in source
    assert "versionBadge" in source
    assert '@click="studioPreviewCompareVersion(artifact)"' in source
    assert '@click="studioPreviewClearCompare()"' in source


def test_reasoning_drawer_exposes_run_artifact_actions() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")
    helpers = _PREVIEW_HELPERS.read_text(encoding="utf-8")

    assert "Artifacts From This Run" in source
    assert "Current product" in helpers
    assert "Source artifact" in helpers
    assert "Sibling product" in helpers
    assert "Render failed" in source
    assert "roleBadge" in source
    assert "Retry render" in source
    assert '@click="openReasoningArtifactPreview(artifact)"' in source
    assert ':href="reasoningArtifactDownloadHref(artifact)"' in source
    assert '@click="promoteReasoningArtifact(artifact)"' in source
    assert "Render to Studio" in source


def test_studio_filter_bar_exposes_latest_only_toggle() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")

    assert 'x-model="studio.latestOnly"' in source
    assert '@change="pruneStudioSelectionToFiltered()"' in source
    assert "Latest only" in source


def test_studio_filter_bar_exposes_grouping_control() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")

    assert 'x-model="studio.groupBy"' in source
    assert '<option value="skill">Skill</option>' in source
    assert '<option value="run">Run</option>' in source
    assert '<option value="date">Date</option>' in source
    assert 'x-for="row in studioRenderableRows()"' in source
    assert "Open run" in source


def test_studio_exposes_trash_toggle_and_restore_action() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")

    assert "Studio Trash" in source
    assert "Trash empty." in source
    assert '@click="toggleStudioTrash()"' in source
    assert '@click="restoreTrashedStudioArtifact(artifact)"' in source


def test_skills_expose_run_trash_and_restore_action() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")

    assert "Run Trash" in source
    assert "Run trash empty." in source
    assert '@click="toggleSkillRunTrash()"' in source
    assert '@click="restoreSkillRun(skills.current?.name, run.trash_id)"' in source