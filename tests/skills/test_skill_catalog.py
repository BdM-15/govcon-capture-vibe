import json
from pathlib import Path

from src.skills.skill_catalog import SkillCatalog, slug_from_github_url


def test_skill_catalog_discovers_skill_and_detail(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    ledger_path = tmp_path / "skills.json"
    skill_dir = skills_dir / "demo-skill"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "assets").mkdir()
    (skill_dir / "scripts").mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo\nmetadata:\n  runtime: tools\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    (skill_dir / "references" / "guide.md").write_text("hi", encoding="utf-8")
    (skill_dir / "assets" / "style.css").write_text("body{}", encoding="utf-8")
    (skill_dir / "scripts" / "run.py").write_text("print('x')", encoding="utf-8")

    catalog = SkillCatalog(skills_dir=skills_dir, ledger_path=ledger_path)

    discovered = catalog.discover()
    detail = catalog.get_skill_detail("demo-skill")

    assert list(discovered) == ["demo-skill"]
    assert detail is not None
    assert detail["references"] == [{"name": "guide.md", "size": "2"}]
    assert detail["assets"] == [{"name": "style.css", "size": "6"}]
    assert detail["scripts"] == [{"name": "run.py", "size": "10"}]


def test_skill_catalog_touch_invocation_persists_ledger(tmp_path: Path) -> None:
    ledger_path = tmp_path / "skills.json"
    catalog = SkillCatalog(skills_dir=tmp_path / "skills", ledger_path=ledger_path)

    catalog.touch_invocation("demo-skill")

    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert payload["demo-skill"]["source"] == "builtin"
    assert payload["demo-skill"]["last_invoked_at"]


def test_slug_from_github_url_strips_git_suffix() -> None:
    assert slug_from_github_url("https://github.com/acme/My-Skill.git") == "my-skill"