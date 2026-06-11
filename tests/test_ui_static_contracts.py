from __future__ import annotations

from pathlib import Path

from src.ui.workbench_assembler import assemble_workbench_html


_ROOT = Path(__file__).parent.parent
_UI_STATIC_ROOT = _ROOT / "src" / "ui" / "static"


def _index_html() -> str:
    return assemble_workbench_html(str(_UI_STATIC_ROOT))
_PREVIEW_HELPERS = _ROOT / "src" / "ui" / "static" / "app" / "theseus-preview-helpers.js"
_CHAIN_HELPERS = _ROOT / "src" / "ui" / "static" / "app" / "theseus-chain-helpers.js"
_SKILL_HELPERS = _ROOT / "src" / "ui" / "static" / "app" / "theseus-skill-helpers.js"
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
    source = _index_html()

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


def test_stack_footer_presents_lightrag_first_runtime_not_raganything_peer() -> None:
    source = _index_html()

    assert "lightrag native" in source
    assert "compat layer" not in source
    assert "stats.stack?.raganything" not in source
    assert "raganything v" not in source


def test_studio_filename_button_is_only_preview_trigger() -> None:
    source = _index_html()
    start = source.index('class="studio-filename-btn text-neon-cyan"')
    end = source.index("</button>", start)
    filename_button = source[start:end]

    assert '@click="openStudioPreview(row.deliverable)"' in filename_button
    assert 'x-text="d.filename"' not in filename_button
    assert 'title="Preview inline"' not in source


def test_studio_preview_header_hides_raw_filename_subline() -> None:
    source = _index_html()
    start = source.index('x-text="studioPreview.deliverable && (studioPreview.deliverable.display_name || studioPreview.deliverable.filename)"')
    end = source.index('x-show="studioPreview.deliverable"', start)
    header_slice = source[start:end]

    assert 'x-show="studioPreview.deliverable && studioPreview.deliverable.display_name && studioPreview.deliverable.display_name !== studioPreview.deliverable.filename"' not in header_slice


def test_studio_preview_keeps_reasoning_link_without_provenance_rail() -> None:
    source = _index_html()

    assert "Full reasoning" in source
    assert '<aside class="studio-provenance-rail">' not in source
    assert "Run Artifacts" not in source
    assert "Transcript Steps" not in source
    assert 'x-show="studioPreview.provenanceLoading"' not in source
    assert 'x-for="artifact in studioPreviewArtifacts()"' not in source


def test_studio_preview_exposes_version_history_and_compare() -> None:
    source = _index_html()
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
    source = _index_html()
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


def test_studio_filter_bar_exposes_grouping_control() -> None:
    source = _index_html()

    assert 'x-model="studio.groupBy"' in source
    assert '<option value="chain">Chain</option>' in source
    assert '<option value="skill">Skill</option>' in source
    assert '<option value="run">Run</option>' in source
    assert '<option value="date">Date</option>' in source
    assert 'x-for="row in studioRenderableRows()"' in source
    assert "Open run" in source


def test_studio_exposes_trash_toggle_and_restore_action() -> None:
    source = _index_html()

    assert "Studio Trash" in source
    assert "Trash empty." in source
    assert '@click="toggleStudioTrash()"' in source
    assert '@click="emptyStudioTrash()"' in source
    assert '@click="restoreTrashedStudioArtifact(artifact)"' in source


def test_skills_expose_run_trash_and_restore_action() -> None:
    source = _index_html()

    assert "Run Trash" in source
    assert "Run trash empty." in source
    assert '@click="toggleSkillRunTrash()"' in source
    assert '@click="restoreSkillRun(skills.current?.name, run.trash_id)"' in source


def test_skills_expose_resume_panel_for_interrupted_runs() -> None:
    source = _index_html()
    helpers = _SKILL_HELPERS.read_text(encoding="utf-8")

    assert 'x-show="skillRunInputRequest(skills.run)"' in source
    assert 'id="skill-run-input-request-panel-template"' in source
    assert 'x-effect="if (skillRunInputRequest(skills.run)) mountSkillRunInputPanel($el)"' in source
    assert '@input="if (skills.run) skills.resumeDrafts[skills.run.run_id] = $event.target.value"' in source
    assert '@submit.prevent="resumeSkillRun(skills.current?.name, skills.run.run_id)"' in source
    assert "window.theseusSkillRunInputRequest" in helpers
    assert "window.theseusResumeSkillRun" in helpers
    assert "window.theseusMountSkillRunInputPanel" in helpers


def test_skill_run_missing_input_panel_reuses_chat_like_composer_language() -> None:
    source = _index_html()
    helpers = _SKILL_HELPERS.read_text(encoding="utf-8")

    first_panel_start = source.index('id="skill-run-input-request-panel-template"')
    first_panel_end = source.index('id="chain-input-request-panel-template"')
    panel_slice = source[first_panel_start:first_panel_end]

    assert "bubble-assistant" in panel_slice
    assert "bubble-user" in panel_slice
    assert "composer-bar" in panel_slice
    assert "Reply to continue this skill" in panel_slice
    assert "send-horizontal" in panel_slice
    assert "Reply in Missing Input composer, then click Resume." in helpers
    assert source.count("Reply to continue this skill") == 1


def test_studio_chain_trace_exposes_resume_action_for_resumeable_chain() -> None:
    source = _index_html()
    helpers = _CHAIN_HELPERS.read_text(encoding="utf-8")

    assert 'x-show="chainCanResume(chains.current)"' in source
    assert '@click="resumeChain(chains.current.chain_id)"' in source
    assert 'x-show="primaryChain(row.deliverable)?.can_resume"' in source
    assert '@click="resumeStudioChain(row.deliverable)"' in source
    assert "window.theseusChainCanResume" in helpers
    assert "window.theseusResumeStudioChain" in helpers


def test_chain_trace_exposes_missing_input_resume_panel() -> None:
    source = _index_html()
    helpers = _CHAIN_HELPERS.read_text(encoding="utf-8")

    assert 'x-show="chainInputRequest(chains.current)"' in source
    assert 'id="chain-input-request-panel-template"' in source
    assert 'x-init="mountChainInputPanel($el)"' in source
    assert 'x-model="chains.resumeDrafts[chains.current.chain_id]"' in source
    assert ':placeholder="chainResumePlaceholder(chains.current)"' in source
    assert "window.theseusChainInputRequest" in helpers
    assert "window.theseusChainResumePlaceholder" in helpers
    assert "window.theseusMountChainInputPanel" in helpers


def test_chain_trace_missing_input_panel_reuses_chat_like_composer_language() -> None:
    source = _index_html()
    helpers = _CHAIN_HELPERS.read_text(encoding="utf-8")

    first_panel_start = source.index('id="chain-input-request-panel-template"')
    first_panel_end = source.rindex('</template>')
    panel_slice = source[first_panel_start:first_panel_end]

    assert "bubble-assistant" in panel_slice
    assert "bubble-user" in panel_slice
    assert "composer-bar" in panel_slice
    assert "Reply to unblock this chain" in panel_slice
    assert "send-horizontal" in panel_slice
    assert "Reply in the Missing Input composer, then click Resume." in helpers
    assert source.count("Reply to unblock this chain") == 1
    assert source.count('x-init="mountChainInputPanel($el)"') == 2


def test_intel_briefings_expose_optional_slice_context_field() -> None:
    source = _index_html()
    intel_helpers = (
        _ROOT / "src" / "ui" / "static" / "app" / "theseus-intel-helpers.js"
    ).read_text(encoding="utf-8")
    intel_view = (
        _ROOT / "src" / "ui" / "static" / "views" / "intel-view.html"
    ).read_text(encoding="utf-8")

    assert 'x-model="intel.sliceContext[slice.id]"' in source
    assert "user_addendum" in intel_helpers
    assert "theseusIntelSliceContextText" in intel_helpers
    assert "openIntelBriefingGuide(slice)" in intel_view
    assert "intel.briefingGuide.open" in intel_view
    assert "tuning-guide-body" in intel_view
    assert "theseusOpenIntelBriefingGuide" in intel_helpers
    assert 'class="settings-label-tip"' in intel_view
    assert "intelContextTooltip(slice)" in intel_view
    assert "theseusIntelContextTooltip" in intel_helpers
    assert 'data-lucide="info"' not in intel_view


def test_chain_helpers_support_partial_status_and_chain_grouping() -> None:
    preview_helpers = _PREVIEW_HELPERS.read_text(encoding="utf-8")
    chain_helpers = _CHAIN_HELPERS.read_text(encoding="utf-8")

    assert 'if (status === "partial")' in chain_helpers
    assert 'if (typeof chain.can_resume === "boolean") return chain.can_resume;' in chain_helpers
    assert '["failed", "partial", "skipped", "pending", "running"]' in chain_helpers
    assert 'if (mode === "chain")' in preview_helpers
    assert 'metaPrefix: "Chain · " + (chain.status || "unknown")' in preview_helpers
    assert 'metaPrefix: "Single run · " + skill' in preview_helpers