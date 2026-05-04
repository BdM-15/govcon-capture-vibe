from pathlib import Path

from src.skills.skill_emitters import auto_emit_artifacts
from src.skills.skill_models import Skill, SkillFrontmatter


def _skill(tmp_path: Path) -> Skill:
    skill_dir = tmp_path / "demo-skill"
    (skill_dir / "assets").mkdir(parents=True)
    return Skill(
        name="demo-skill",
        path=str(skill_dir),
        skill_md_path=str(skill_dir / "SKILL.md"),
        frontmatter=SkillFrontmatter(name="demo-skill", description="desc"),
        body_md="body",
    )


def _renderer_script(path: Path) -> None:
    path.write_text(
        "import argparse\n"
        "from pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--input')\n"
        "parser.add_argument('--output')\n"
        "parser.add_argument('--reference', required=False)\n"
        "parser.add_argument('--title', required=False)\n"
        "args = parser.parse_args()\n"
        "Path(args.output).write_text('rendered', encoding='utf-8')\n",
        encoding="utf-8",
    )


def test_auto_emit_artifacts_writes_reports_and_renderer_outputs(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "response.md").write_text("hello world", encoding="utf-8")

    repo_root = tmp_path / "repo"
    renderers_dir = repo_root / ".github" / "skills" / "renderers" / "scripts"
    renderers_dir.mkdir(parents=True)
    _renderer_script(renderers_dir / "render_docx.py")
    _renderer_script(renderers_dir / "render_xlsx.py")

    auto_emit_artifacts(skill, run_dir, repo_root=repo_root)

    artifacts_dir = run_dir / "artifacts"
    assert (artifacts_dir / "report.md").read_text(encoding="utf-8") == "hello world"
    assert (artifacts_dir / "report.json").is_file()
    assert (artifacts_dir / "demo-skill_report.docx").is_file()
    assert (artifacts_dir / "demo-skill_report.xlsx").is_file()
    assert (run_dir / "tool_outputs" / "render_docx.stdout.txt").is_file()
    assert (run_dir / "tool_outputs" / "render_xlsx.stderr.txt").is_file()


def test_auto_emit_artifacts_noops_without_response(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    auto_emit_artifacts(skill, run_dir, repo_root=tmp_path)

    assert not (run_dir / "artifacts" / "report.md").exists()