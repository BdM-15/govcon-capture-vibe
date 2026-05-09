"""Phase 174.1 — dual skill-root discovery (primary + vendor extras)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.skills.skill_catalog import SkillCatalog


def _write_skill(root: Path, name: str, body: str = "body") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} desc\n---\n\n# {name}\n{body}\n",
        encoding="utf-8",
    )
    return skill_dir


def test_discovery_walks_primary_then_extras(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    vendor = tmp_path / "vendor"
    _write_skill(primary, "alpha")
    _write_skill(vendor, "beta")

    catalog = SkillCatalog(
        skills_dir=primary,
        ledger_path=tmp_path / "skills.json",
        extra_dirs=[vendor],
    )
    discovered = catalog.discover()

    assert sorted(discovered) == ["alpha", "beta"]
    assert Path(discovered["alpha"].path).parent == primary
    assert Path(discovered["beta"].path).parent == vendor


def test_primary_root_wins_on_name_collision(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    primary = tmp_path / "primary"
    vendor = tmp_path / "vendor"
    primary_dir = _write_skill(primary, "shared", body="primary version")
    vendor_dir = _write_skill(vendor, "shared", body="vendor version")

    catalog = SkillCatalog(
        skills_dir=primary,
        ledger_path=tmp_path / "skills.json",
        extra_dirs=[vendor],
    )
    with caplog.at_level("WARNING"):
        discovered = catalog.discover()

    assert list(discovered) == ["shared"]
    # Primary copy wins.
    assert Path(discovered["shared"].path) == primary_dir
    # Vendor copy was logged as suppressed.
    assert any(
        "Skill name collision" in rec.message and str(vendor_dir) in rec.message
        for rec in caplog.records
    )


def test_missing_extra_dir_is_silent(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    _write_skill(primary, "alpha")
    missing_vendor = tmp_path / "does-not-exist"

    catalog = SkillCatalog(
        skills_dir=primary,
        ledger_path=tmp_path / "skills.json",
        extra_dirs=[missing_vendor],
    )
    discovered = catalog.discover()
    assert list(discovered) == ["alpha"]


def test_default_manager_includes_vendor_root() -> None:
    """Smoke test: with no overrides, the manager registers the vendor root.

    Validates the wiring in ``SkillManager.__init__`` (epic 174.1) without
    asserting on which vendored skills are present — those entries change
    over time as the vendor manifest evolves.
    """
    from src.skills.manager import SkillManager, _SKILLS_DIR, _VENDOR_SKILLS_DIR

    mgr = SkillManager()
    assert mgr.skills_dir == _SKILLS_DIR
    assert _VENDOR_SKILLS_DIR in mgr.extra_skills_dirs


def test_custom_skills_dir_drops_default_extras(tmp_path: Path) -> None:
    """Tests that pass a tmp ``skills_dir`` should not accidentally pick up
    the vendor root and pollute their isolation."""
    from src.skills.manager import SkillManager

    mgr = SkillManager(skills_dir=tmp_path / "isolated")
    assert mgr.extra_skills_dirs == []
