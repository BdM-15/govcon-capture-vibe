from pathlib import Path

from src.skills.manager import SkillManager
from src.skills.studio_surfaces import (
    deck_display_name,
    finalize_huashu_studio_surfaces,
    iter_studio_deliverable_paths,
    validate_deck_index,
)


def _deck_index(manifest: list[dict[str, str]]) -> str:
    entries = ",\n    ".join(
        f'{{ "file": "{item["file"]}", "label": "{item["label"]}" }}'
        for item in manifest
    )
    return (
        "<!DOCTYPE html><html><head><title>MCPP Briefing Deck</title>"
        f"<script>window.DECK_MANIFEST = [\n    {entries}\n  ];</script>"
        "</head><body></body></html>"
    )


def test_iter_studio_deliverable_paths_surfaces_nested_deck_index(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    deck_dir = artifacts / "briefing-deck" / "slides"
    deck_dir.mkdir(parents=True)
    (deck_dir / "01-cover.html").write_text("<html>cover</html>", encoding="utf-8")
    (artifacts / "briefing-deck" / "index.html").write_text(
        _deck_index([{"file": "slides/01-cover.html", "label": "Cover"}]),
        encoding="utf-8",
    )
    (artifacts / "huashu_design_brief.docx").write_bytes(b"docx")

    paths = dict(iter_studio_deliverable_paths(artifacts))

    assert "briefing-deck/index.html" in paths
    assert "huashu_design_brief.docx" in paths
    assert "briefing-deck/slides/01-cover.html" not in paths


def test_validate_deck_index_reports_missing_slides(tmp_path: Path) -> None:
    deck_dir = tmp_path / "briefing-deck"
    (deck_dir / "slides").mkdir(parents=True)
    (deck_dir / "slides" / "01-cover.html").write_text("<html>cover</html>", encoding="utf-8")
    (deck_dir / "index.html").write_text(
        _deck_index(
            [
                {"file": "slides/01-cover.html", "label": "Cover"},
                {"file": "slides/02-executive.html", "label": "Executive"},
            ]
        ),
        encoding="utf-8",
    )

    status = validate_deck_index(deck_dir / "index.html")

    assert status["expected"] == 2
    assert status["found"] == 1
    assert status["complete"] is False
    assert "slides/02-executive.html" in status["missing"]


def test_finalize_huashu_studio_surfaces_writes_manifest_and_warns(
    tmp_path: Path,
) -> None:
    artifacts = tmp_path / "artifacts"
    deck_dir = artifacts / "briefing-deck" / "slides"
    deck_dir.mkdir(parents=True)
    (deck_dir / "01-cover.html").write_text("<html>cover</html>", encoding="utf-8")
    (artifacts / "briefing-deck" / "index.html").write_text(
        _deck_index(
            [
                {"file": "slides/01-cover.html", "label": "Cover"},
                {"file": "slides/02-executive.html", "label": "Executive"},
            ]
        ),
        encoding="utf-8",
    )

    warnings = finalize_huashu_studio_surfaces(tmp_path)

    assert warnings
    assert "1/2 slides" in warnings[0]
    assert deck_display_name(artifacts / "briefing-deck" / "index.html") == "MCPP Briefing Deck"


def test_list_deliverables_hides_huashu_docx_and_surfaces_nested_deck(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "skill_runs" / "huashu-design" / "20260611_163708_design_briefing_deck"
    deck_dir = run_dir / "artifacts" / "briefing-deck" / "slides"
    deck_dir.mkdir(parents=True)
    (deck_dir / "01-cover.html").write_text("<html>cover</html>", encoding="utf-8")
    (run_dir / "artifacts" / "briefing-deck" / "index.html").write_text(
        _deck_index([{"file": "slides/01-cover.html", "label": "Cover"}]),
        encoding="utf-8",
    )
    (run_dir / "artifacts" / "huashu_design_brief.docx").write_bytes(b"docx")
    (run_dir / "run.md").write_text(
        "---\nrun_id: 20260611_163708_design_briefing_deck\n"
        "skill: huashu-design\nworkspace: ws\ncreated_at: 2026-06-11T16:37:08Z\n"
        "elapsed_ms: 1\nentities_used: []\nresponse_chars: 1\n---\n",
        encoding="utf-8",
    )

    rows = SkillManager().list_deliverables(tmp_path)

    assert len(rows) == 1
    assert rows[0]["filename"] == "briefing-deck/index.html"
    assert rows[0]["display_name"] == "MCPP Briefing Deck"
    assert rows[0]["deck_slides_expected"] == 1


def test_get_artifact_path_resolves_nested_relative_paths(tmp_path: Path) -> None:
    from src.skills.runs import SkillRunStore

    run_dir = tmp_path / "skill_runs" / "huashu-design" / "20260611_163708_design_briefing_deck"
    artifact = run_dir / "artifacts" / "briefing-deck" / "index.html"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("<html>deck</html>", encoding="utf-8")

    store = SkillRunStore()
    resolved = store.get_artifact_path(
        tmp_path,
        "huashu-design",
        "20260611_163708_design_briefing_deck",
        "briefing-deck/index.html",
    )

    assert resolved == artifact.resolve()


def test_huashu_skill_metadata_disables_auto_emit() -> None:
    from src.skills import get_skill_manager

    skill = get_skill_manager().get_skill("huashu-design")
    assert skill is not None
    assert skill.frontmatter.metadata.get("auto_emit_artifacts") is False