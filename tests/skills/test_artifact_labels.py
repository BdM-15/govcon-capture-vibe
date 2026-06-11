"""Unit tests for content-derived Studio artifact labels."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.artifact_labels import (
    derive_run_content_title,
    extract_markdown_h1,
    extract_prompt_variant,
    fallback_content_title,
    format_product_display_name,
    humanize_run_label,
    inject_prompt_variant,
    is_generic_studio_label,
    is_weak_content_title,
    maybe_enrich_display_name_with_prompt,
    normalize_content_title,
    resolve_studio_display_name,
    strip_skill_label_from_title,
)


def test_humanize_run_label_formats_timestamp_and_topic() -> None:
    label = humanize_run_label("20260611_163708_design_briefing_deck_from_attach")
    assert label.startswith("11 Jun 16:37")
    assert "design briefing deck from attach" in label


def test_extract_markdown_h1_reads_first_heading() -> None:
    assert extract_markdown_h1("# Mission Readiness Frame — MCPP RFP\n\nbody") == (
        "Mission Readiness Frame — MCPP RFP"
    )


def test_strip_skill_label_from_title_removes_profile_prefix_and_suffix() -> None:
    assert (
        strip_skill_label_from_title(
            "Mission Readiness Frame — MCPP RFP (M67004-26-R-0007)",
            "mission-readiness-framer",
        )
        == "MCPP RFP (M67004-26-R-0007)"
    )
    assert (
        strip_skill_label_from_title("MCPP Competitive Intel Brief", "competitive-intel")
        == "MCPP Brief"
    )
    assert strip_skill_label_from_title("Competitive Intel", "competitive-intel") is None
    assert (
        strip_skill_label_from_title("Mission Readiness Frame Brief", "mission-readiness-framer")
        is None
    )


def test_derive_run_content_title_from_mission_readiness_brief(tmp_path: Path) -> None:
    run_dir = tmp_path / "skill_runs" / "mission-readiness-framer" / "20260611_151031_frame"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "brief.md").write_text(
        "# Mission Readiness Frame — MCPP RFP (M67004-26-R-0007)\n",
        encoding="utf-8",
    )

    title = derive_run_content_title("mission-readiness-framer", run_dir)

    assert title == "MCPP RFP (M67004-26-R-0007)"


def test_format_product_display_name_adds_brief_suffix_without_duplication() -> None:
    assert (
        format_product_display_name(
            "MCPP RFP (M67004-26-R-0007)",
            filename="mission_readiness_frame_brief.docx",
            ext="docx",
        )
        == "MCPP RFP (M67004-26-R-0007) · Brief"
    )
    assert (
        format_product_display_name(
            "FA805122F0001 Task Order Burn Brief",
            filename="competitive_intel_brief.docx",
            ext="docx",
        )
        == "FA805122F0001 Task Order Burn Brief"
    )


def test_is_generic_studio_label_detects_profile_fallbacks() -> None:
    assert is_generic_studio_label(
        "Competitive Intel Brief",
        skill_name="competitive-intel",
        filename="competitive_intel_brief.docx",
    )
    assert not is_generic_studio_label(
        "FA805122F0001 Task Order Burn Brief",
        skill_name="competitive-intel",
        filename="competitive_intel_brief.docx",
    )


def test_resolve_studio_display_name_backfills_generic_manifest(tmp_path: Path) -> None:
    run_dir = tmp_path / "skill_runs" / "mission-readiness-framer" / "20260611_151031_frame"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "brief.md").write_text(
        "# Mission Readiness Frame — MCPP RFP (M67004-26-R-0007)\n",
        encoding="utf-8",
    )
    (artifacts / "mission_readiness_frame_brief.docx").write_bytes(b"docx")

    resolved = resolve_studio_display_name(
        skill_name="mission-readiness-framer",
        run_dir=run_dir,
        artifact_rel="mission_readiness_frame_brief.docx",
        manifest_entry={"display_name": "Mission Readiness Frame Brief"},
    )

    assert resolved == "MCPP RFP (M67004-26-R-0007) · Brief"


def test_resolve_studio_display_name_keeps_specific_manifest(tmp_path: Path) -> None:
    run_dir = tmp_path / "skill_runs" / "competitive-intel" / "20260428_130000_second"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "burn.html").write_bytes(b"<html></html>")

    resolved = resolve_studio_display_name(
        skill_name="competitive-intel",
        run_dir=run_dir,
        artifact_rel="burn.html",
        manifest_entry={"display_name": "AFCAP V Parent Vehicle Burn Intel"},
    )

    assert resolved == "AFCAP V Parent Vehicle Burn Intel"


def test_fallback_content_title_uses_run_topic_not_skill_slug(tmp_path: Path) -> None:
    run_dir = tmp_path / "skill_runs" / "future-skill" / "20260611_120000_emit_product"
    (run_dir / "artifacts").mkdir(parents=True)

    title = fallback_content_title(
        "future-skill",
        run_dir,
        "future_skill_brief.docx",
    )

    assert title == "emit product"


def test_normalize_content_title_strips_competitive_intel_suffix() -> None:
    assert (
        normalize_content_title("FA805122F0001 Competitive Intel", "competitive-intel")
        == "FA805122F0001"
    )


def test_derive_run_content_title_reads_huashu_deck_title(tmp_path: Path) -> None:
    run_dir = tmp_path / "skill_runs" / "huashu-design" / "20260611_163708_design_briefing_deck"
    deck_dir = run_dir / "artifacts" / "briefing-deck"
    deck_dir.mkdir(parents=True)
    (deck_dir / "index.html").write_text(
        "<html><head><title>MCPP Briefing Deck</title></head>"
        "<body><script>window.DECK_MANIFEST = [];</script></body></html>",
        encoding="utf-8",
    )

    title = derive_run_content_title("huashu-design", run_dir)

    assert title == "MCPP Briefing Deck"


def test_extract_prompt_variant_strips_boilerplate_and_caps_length() -> None:
    assert (
        extract_prompt_variant(
            "Please build a mission readiness frame focused on OCI transition risks for MCPP."
        )
        == "mission readiness frame focused on OCI"
    )
    assert (
        extract_prompt_variant(
            "Build the mission readiness frame from the full solicitation package"
        )
        == "mission readiness frame"
    )


def test_inject_prompt_variant_inserts_before_product_suffix() -> None:
    assert (
        inject_prompt_variant("MCPP RFP (M67004-26-R-0007) · Brief", "OCI transition focus")
        == "MCPP RFP (M67004-26-R-0007) · OCI transition focus · Brief"
    )


def test_maybe_enrich_display_name_adds_variant_for_weak_titles(tmp_path: Path) -> None:
    run_dir = tmp_path / "skill_runs" / "future-skill" / "20260611_120000_emit_product"
    run_dir.mkdir(parents=True)
    (run_dir / "artifacts").mkdir()
    (run_dir / "run.md").write_text(
        "---\nrun_id: 20260611_120000_emit_product\nskill: future-skill\n---\n\n"
        "## User Prompt\n\nemit a product with OCI emphasis for MCPP\n",
        encoding="utf-8",
    )

    enriched = maybe_enrich_display_name_with_prompt(
        "emit product · Brief",
        skill_name="future-skill",
        run_dir=run_dir,
        artifact_rel="future_skill_brief.docx",
    )

    assert enriched == "emit product · emit a product with OCI emphasis for MCPP · Brief"


def test_maybe_enrich_skips_strong_content_titles(tmp_path: Path) -> None:
    run_dir = tmp_path / "skill_runs" / "mission-readiness-framer" / "20260611_151031_frame"
    run_dir.mkdir(parents=True)
    (run_dir / "artifacts").mkdir()
    (run_dir / "run.md").write_text(
        "---\nrun_id: 20260611_151031_frame\nskill: mission-readiness-framer\n---\n\n"
        "## User Prompt\n\nRe-run with transition-risk emphasis\n",
        encoding="utf-8",
    )

    title = "MCPP RFP (M67004-26-R-0007) · Brief"
    assert not is_weak_content_title(
        title,
        skill_name="mission-readiness-framer",
        run_dir=run_dir,
        artifact_rel="mission_readiness_frame_brief.docx",
    )
    assert (
        maybe_enrich_display_name_with_prompt(
            title,
            skill_name="mission-readiness-framer",
            run_dir=run_dir,
            artifact_rel="mission_readiness_frame_brief.docx",
        )
        == title
    )


def test_derive_run_content_title_from_frame_json_when_brief_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / "skill_runs" / "mission-readiness-framer" / "20260611_151031_frame"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "mission_readiness_frame.json").write_text(
        json.dumps(
            {
                "opportunity_context": {
                    "solicitation_id": "M67004-26-R-0007",
                    "agency": "USMC",
                }
            }
        ),
        encoding="utf-8",
    )

    title = derive_run_content_title("mission-readiness-framer", run_dir)

    assert title == "USMC (M67004-26-R-0007)"