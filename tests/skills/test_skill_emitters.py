from pathlib import Path
import json
import subprocess

from src.skills.skill_emitters import auto_emit_artifacts
from src.skills.skill_models import Skill, SkillFrontmatter
from src.skills.tool_competitive_intel import build_competitive_intel_brief_markdown


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


def _office_skill(tmp_path: Path) -> Skill:
    skill = _skill(tmp_path)
    skill.frontmatter.metadata["auto_emit_formats"] = ["md", "json", "docx", "xlsx"]
    skill.frontmatter.metadata["auto_emit_xlsx_source"] = "table.json"
    return skill


def _competitive_intel_skill(tmp_path: Path) -> Skill:
    skill_dir = tmp_path / "competitive-intel"
    (skill_dir / "assets").mkdir(parents=True)
    return Skill(
        name="competitive-intel",
        path=str(skill_dir),
        skill_md_path=str(skill_dir / "SKILL.md"),
        frontmatter=SkillFrontmatter(name="competitive-intel", description="desc"),
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
        "parser.add_argument('--metadata', action='append', required=False)\n"
        "args = parser.parse_args()\n"
        "Path(args.output).write_text('rendered', encoding='utf-8')\n",
        encoding="utf-8",
    )


def test_auto_emit_artifacts_writes_reports_by_default(tmp_path: Path) -> None:
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
    assert (artifacts_dir / "demo_skill_brief.docx").is_file()
    assert not (artifacts_dir / "demo-skill_final.html").exists()
    assert not (artifacts_dir / "demo_skill_report.xlsx").exists()


def test_auto_emit_artifacts_writes_office_outputs_when_opted_in(tmp_path: Path) -> None:
    skill = _office_skill(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "response.md").write_text("hello world", encoding="utf-8")
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "table.json").write_text(
        '[{"contract":"ABC-123","annual_burn_usd":1200.0}]',
        encoding="utf-8",
    )

    repo_root = tmp_path / "repo"
    renderers_dir = repo_root / ".github" / "skills" / "renderers" / "scripts"
    renderers_dir.mkdir(parents=True)
    _renderer_script(renderers_dir / "render_docx.py")
    _renderer_script(renderers_dir / "render_xlsx.py")

    auto_emit_artifacts(skill, run_dir, repo_root=repo_root)

    assert (artifacts_dir / "demo_skill_brief.docx").is_file()
    assert (artifacts_dir / "table.xlsx").is_file()
    assert (run_dir / "tool_outputs" / "render_docx.stdout.txt").is_file()
    assert (run_dir / "tool_outputs" / "render_xlsx_table.stderr.txt").is_file()


def test_auto_emit_artifacts_noops_without_response(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    auto_emit_artifacts(skill, run_dir, repo_root=tmp_path)

    assert not (run_dir / "artifacts" / "report.md").exists()


def test_auto_emit_artifacts_shapes_competitive_intel_brief(tmp_path: Path) -> None:
        skill = _competitive_intel_skill(tmp_path)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "response.md").write_text("raw response blob", encoding="utf-8")
        artifacts_dir = run_dir / "artifacts"
        artifacts_dir.mkdir()
        (artifacts_dir / "competitive_intel_obligation.json").write_text(
                """
                {
                    "input_contract_number": "FA805122F0001",
                    "resolved": {"scenario": "idiq_order"},
                    "hierarchy": {"parent_award_id": "CONT_IDV_PARENT"},
                    "obligations": {
                        "total_obligated_usd": 44070085.27,
                        "net_obligated_usd": 43659700.13,
                        "rate_analysis": {"monthly_burn_usd": 698555.2, "annual_burn_usd": 8382662.42, "daily_burn_usd": 23297.6},
                        "by_transaction": [
                            {"modification_number": "P00005", "action_type": "G", "action_date": "2022-11-17", "amount_usd": 9183672.0},
                            {"modification_number": "P00007", "action_type": "B", "action_date": "2024-05-23", "amount_usd": -350385.14},
                            {"modification_number": "P00014", "action_type": "G", "action_date": "2025-11-14", "amount_usd": 8369667.0, "modification_description": "Exercise option four"}
                        ]
                    },
                    "insights": {
                        "headline": "Clean burn story.",
                        "blocks": [
                            {
                                "id": "burn_posture",
                                "evidence": {"recommended_ptw_baseline_usd": 8388921.37, "pop_end_potential": "2026-12-15"}
                            },
                            {
                                "id": "award_story",
                                "summary": "One award story across base and options.",
                                "evidence": {
                                    "period_of_performance_segments": [
                                        {"label": "Base period", "pop_start_date": "2021-10-28", "pop_end_date": "2022-11-17", "months": 13.0, "obligated_usd": 9229200.0, "monthly_rate_usd": 709938.46},
                                        {"label": "Option period 1", "pop_start_date": "2022-11-17", "pop_end_date": "2023-11-20", "months": 12.5, "obligated_usd": 9183672.0, "monthly_rate_usd": 734693.76}
                                    ]
                                }
                            }
                        ]
                    },
                    "vehicle_context": {"child_order_count": 22, "net_obligated_usd": 390322586.54},
                    "competitor_discovery": {"completeness_status": "high", "parent_vehicle_awardee_count": 8, "order_holder_count": 1},
                    "warnings": []
                }
                """,
                encoding="utf-8",
        )
        repo_root = tmp_path / "repo"
        renderers_dir = repo_root / ".github" / "skills" / "renderers" / "scripts"
        renderers_dir.mkdir(parents=True)
        _renderer_script(renderers_dir / "render_docx.py")
        _renderer_script(renderers_dir / "render_xlsx.py")

        auto_emit_artifacts(skill, run_dir, repo_root=repo_root)

        brief = (artifacts_dir / "competitive_intel_brief.md").read_text(encoding="utf-8")
        manifest = json.loads((run_dir / "artifacts_manifest.json").read_text(encoding="utf-8"))
        assert brief.startswith("# FA805122F0001 Order Burn Brief\n\nClean burn story.")
        assert "## Snapshot" in brief
        assert "- Scenario: Single order" in brief
        assert "## Burn posture" in brief
        assert "## Award story by period of performance" in brief
        assert "One award story across base and options." in brief
        assert "- Base period: 2021-10-28 to 2022-11-17; $9.23M obligated;" in brief
        assert "$709.9K/month; 13.0 months." in brief
        assert "## Inflection Points" in brief
        assert "- P00014 on 2025-11-14: Exercise option four; $8.37M." in brief
        assert "## Caveats" in brief
        assert "- No collector caveats reported." in brief
        assert manifest["report.md"]["display_name"] == "FA805122F0001 Order Burn Final Response"
        assert manifest["competitive_intel_brief.md"]["display_name"] == "FA805122F0001 Order Burn Brief Source"
        assert manifest["competitive_intel_brief.docx"]["display_name"] == "FA805122F0001 Order Burn Brief"
        assert manifest["competitive_intel_obligation.xlsx"]["display_name"] == "FA805122F0001 Order Burn Workbook"


def test_build_competitive_intel_brief_markdown_keeps_vehicle_story_sharp() -> None:
    brief = build_competitive_intel_brief_markdown(
        {
            "input_contract_number": "PARENT-001",
            "resolved": {"scenario": "parent_idiq", "piid": "PARENT-001"},
            "hierarchy": {"parent_award_id": "CONT_IDV_PARENT"},
            "obligations": {
                "total_obligated_usd": 525.0,
                "net_obligated_usd": 500.0,
                "by_transaction": [
                    {
                        "modification_number": "P00012",
                        "action_date": "2024-09-01",
                        "action_type_description": "EXERCISE AN OPTION",
                        "modification_description": "Option exercised",
                        "amount_usd": 300.0,
                    },
                    {
                        "modification_number": "P00009",
                        "action_date": "2024-05-01",
                        "action_type_description": "OTHER",
                        "modification_description": "Bridge mod",
                        "amount_usd": -25.0,
                    },
                ],
            },
            "vehicle_context": {"child_order_count": 2, "net_obligated_usd": 500.0},
            "competitor_discovery": {"completeness_status": "high"},
            "ptw_seed": {"recommended_baseline_usd": 500.0},
            "insights": {
                "headline": "PARENT-001 rolls up $500.00 net across 2 child orders.",
                "blocks": [
                    {
                        "id": "burn_posture",
                        "title": "Burn posture",
                        "summary": "Vehicle burn is concentrated and stable.",
                        "evidence": {
                            "monthly_burn_usd": 41.67,
                            "annual_burn_usd": 500.0,
                            "daily_burn_usd": 1.37,
                            "pop_end_current": "2024-12-31",
                            "pop_end_potential": "2025-12-31",
                            "recommended_ptw_baseline_usd": 500.0,
                        },
                    },
                    {
                        "id": "vehicle_concentration",
                        "title": "Vehicle concentration",
                        "summary": "Burn is concentrated in ORDER-2.",
                        "evidence": {
                            "top_child_orders": [
                                {
                                    "piid": "ORDER-2",
                                    "amount_usd": 300.0,
                                    "share_of_net_obligations_pct": 60.0,
                                },
                                {
                                    "piid": "ORDER-1",
                                    "amount_usd": 200.0,
                                    "share_of_net_obligations_pct": 40.0,
                                },
                            ]
                        },
                    },
                    {
                        "id": "competitive_context",
                        "title": "Competitive context",
                        "summary": "Roster exact and high confidence.",
                        "evidence": {
                            "parent_vehicle_awardee_count": 2,
                            "order_holder_count": 2,
                            "parent_holder_count": 2,
                            "parent_vehicle_awardees": [
                                {"name": "HOLDCO B"},
                                {"name": "HOLDCO A"},
                            ],
                        },
                    },
                ],
            },
            "warnings": ["POP end dates inferred from modification timing."],
        },
        "Competitive Intel",
    )

    assert "## Vehicle concentration" in brief
    assert "- ORDER-2: $300.00 (60.0% of net)." in brief
    assert "## Competitive context" in brief
    assert "- Exact parent-awardee roster: HOLDCO B; HOLDCO A." in brief
    assert "## Caveats" in brief
    assert "- POP end dates inferred from modification timing." in brief


def test_auto_emit_artifacts_marks_failed_render_on_source_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    skill = _skill(tmp_path)
    skill.frontmatter.metadata["auto_emit_formats"] = ["docx"]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "response.md").write_text("hello world", encoding="utf-8")

    repo_root = tmp_path / "repo"
    renderers_dir = repo_root / ".github" / "skills" / "renderers" / "scripts"
    renderers_dir.mkdir(parents=True)
    _renderer_script(renderers_dir / "render_docx.py")

    class _FailedProc:
        returncode = 2
        stdout = ""
        stderr = "docx renderer blew up"

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: _FailedProc(),
    )

    auto_emit_artifacts(skill, run_dir, repo_root=repo_root)

    manifest = json.loads((run_dir / "artifacts_manifest.json").read_text(encoding="utf-8"))
    entry = manifest["report.md"]
    assert entry["render_status"] == "failed"
    assert entry["render_message"] == "docx renderer blew up"
    assert entry["render_targets"] == ["demo_skill_brief.docx"]
    assert entry["render_logs"] == ["render_docx.stdout.txt", "render_docx.stderr.txt"]
    assert entry["render_log_excerpt"] == "docx renderer blew up"