from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).parent.parent
_INDEX_HTML = _ROOT / "src" / "ui" / "static" / "index.html"
_UI_STATIC_ROOT = _ROOT / "src" / "ui" / "static"
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


def test_studio_filter_bar_exposes_grouping_control() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")

    assert 'x-model="studio.groupBy"' in source
    assert '<option value="chain">Chain</option>' in source
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
    assert '@click="emptyStudioTrash()"' in source
    assert '@click="restoreTrashedStudioArtifact(artifact)"' in source


def test_skills_expose_run_trash_and_restore_action() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")

    assert "Run Trash" in source
    assert "Run trash empty." in source
    assert '@click="toggleSkillRunTrash()"' in source
    assert '@click="restoreSkillRun(skills.current?.name, run.trash_id)"' in source


def test_skills_expose_resume_panel_for_interrupted_runs() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")
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
    source = _INDEX_HTML.read_text(encoding="utf-8")
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


def test_capture_stream_surface_is_wired_end_to_end() -> None:
    """Tracer-bullet UI for #151: a capture tab + input + submit + stream container,
    bound to Alpine state and a helper that POSTs to /api/ui/vault/capture."""
    source = _INDEX_HTML.read_text(encoding="utf-8")
    state = (_ROOT / "src" / "ui" / "static" / "app" / "theseus-state-helpers.js").read_text(encoding="utf-8")
    delegates = (_ROOT / "src" / "ui" / "static" / "app" / "theseus-app-delegates.js").read_text(encoding="utf-8")
    capture_helpers_path = _ROOT / "src" / "ui" / "static" / "app" / "theseus-capture-helpers.js"

    # Markup: tab + surface elements live in the vault section
    assert 'id="vault-tab-capture"' in source
    assert "vaultTab = 'capture'" in source
    assert 'id="vault-capture-input"' in source
    assert 'id="vault-capture-submit"' in source
    assert 'id="vault-capture-stream"' in source

    # Alpine state holds the input body, submit-in-flight flag, and stream array
    assert "vaultCaptureBody:" in state
    assert "vaultCaptureStream:" in state
    assert "vaultCapturing:" in state

    # Delegate hook + helper file + script tag wire the click to the helper
    assert "vaultCaptureSubmit()" in delegates
    assert "window.theseusVaultCaptureSubmit" in delegates
    assert capture_helpers_path.exists(), "Missing theseus-capture-helpers.js"
    helpers = capture_helpers_path.read_text(encoding="utf-8")
    assert "/api/ui/vault/capture" in helpers
    assert "window.theseusVaultCaptureSubmit" in helpers
    assert '<script src="/ui/app/theseus-capture-helpers.js"></script>' in source


def test_capture_stream_surfaces_degraded_polish_state() -> None:
    """#157 UI half: when polish was requested but the orchestrator fell back to raw,
    the user must see a distinct indicator on the resulting card AND a 503 from the
    route must surface a polish-specific toast (not a generic 'capture failed')."""
    source = _INDEX_HTML.read_text(encoding="utf-8")
    capture_helpers = (_ROOT / "src" / "ui" / "static" / "app" / "theseus-capture-helpers.js").read_text(encoding="utf-8")

    # Helper sends auto_polish explicitly so the orchestrator knows intent
    assert '"auto_polish"' in capture_helpers or "auto_polish:" in capture_helpers

    # Helper distinguishes 503 (polish unavailable) from generic failures
    assert "503" in capture_helpers
    assert "Polish" in capture_helpers  # polish-specific copy

    # Helper marks the card when polish was requested but the response came back unpolished
    assert "_degraded" in capture_helpers

    # Card markup renders the degraded indicator conditionally
    capture_section_start = source.index('id="vault-capture-stream"')
    capture_section_end = source.index("<!-- notes tab content", capture_section_start)
    capture_markup = source[capture_section_start:capture_section_end]
    assert "note._degraded" in capture_markup


def test_capture_card_renders_three_state_status_dot() -> None:
    """#153: each card shows a status dot driven by note.status with three
    visual states (raw=pulsing, polished=solid, evergreen=ringed). Pulse
    must respect prefers-reduced-motion."""
    source = _INDEX_HTML.read_text(encoding="utf-8")
    css_path = _ROOT / "src" / "ui" / "static" / "styles" / "theseus.css"
    css = css_path.read_text(encoding="utf-8")

    capture_section_start = source.index('id="vault-capture-stream"')
    capture_section_end = source.index("<!-- notes tab content", capture_section_start)
    capture_markup = source[capture_section_start:capture_section_end]

    # Dot element is bound to note.status with all three lifecycle classes
    assert "capture-status-dot" in capture_markup
    assert "note.status" in capture_markup
    assert "capture-status-raw" in capture_markup
    assert "capture-status-polished" in capture_markup
    assert "capture-status-evergreen" in capture_markup

    # CSS defines the three states + a reduced-motion guard for the raw pulse
    assert ".capture-status-dot" in css
    assert ".capture-status-raw" in css
    assert ".capture-status-polished" in css
    assert ".capture-status-evergreen" in css
    assert "prefers-reduced-motion" in css
    assert "capture-status-raw" in css.split("prefers-reduced-motion", 1)[1]


def test_studio_chain_trace_exposes_resume_action_for_resumeable_chain() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")
    helpers = _CHAIN_HELPERS.read_text(encoding="utf-8")

    assert 'x-show="chainCanResume(chains.current)"' in source
    assert '@click="resumeChain(chains.current.chain_id)"' in source
    assert 'x-show="primaryChain(row.deliverable)?.can_resume"' in source
    assert '@click="resumeStudioChain(row.deliverable)"' in source
    assert "window.theseusChainCanResume" in helpers
    assert "window.theseusResumeStudioChain" in helpers


def test_chain_trace_exposes_missing_input_resume_panel() -> None:
    source = _INDEX_HTML.read_text(encoding="utf-8")
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
    source = _INDEX_HTML.read_text(encoding="utf-8")
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


def test_chain_helpers_support_partial_status_and_chain_grouping() -> None:
    preview_helpers = _PREVIEW_HELPERS.read_text(encoding="utf-8")
    chain_helpers = _CHAIN_HELPERS.read_text(encoding="utf-8")

    assert 'if (status === "partial")' in chain_helpers
    assert 'if (typeof chain.can_resume === "boolean") return chain.can_resume;' in chain_helpers
    assert '["failed", "partial", "skipped", "pending", "running"]' in chain_helpers
    assert 'if (mode === "chain")' in preview_helpers
    assert 'metaPrefix: "Chain · " + (chain.status || "unknown")' in preview_helpers
    assert 'metaPrefix: "Single run · " + skill' in preview_helpers