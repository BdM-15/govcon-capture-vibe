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
                        "rate_analysis": {
                            "pop_start": "2021-10-28",
                            "pop_end_current": "2023-11-20",
                            "pop_end_potential": "2026-12-15",
                            "monthly_burn_usd": 698555.2,
                            "annual_burn_usd": 8382662.42,
                            "daily_burn_usd": 23297.6
                        },
                        "by_fiscal_year": [
                            {"fy": "2022", "amount_usd": 9229200.0},
                            {"fy": "2023", "amount_usd": 9183672.0},
                            {"fy": "2024", "amount_usd": -350385.14},
                            {"fy": "2026", "amount_usd": 8369667.0}
                        ],
                        "by_transaction": [
                            {"modification_number": "0", "action_type": "A", "action_date": "2021-10-28", "action_type_description": "DEFINITIVE CONTRACT", "amount_usd": 9229200.0, "cumulative_obligated_usd": 9229200.0, "modification_description": null},
                            {"modification_number": "P00005", "action_type": "G", "action_date": "2022-11-17", "action_type_description": "EXERCISE OPTION", "amount_usd": 9183672.0, "cumulative_obligated_usd": 18412872.0, "modification_description": "Exercise option one"},
                            {"modification_number": "P00007", "action_type": "B", "action_date": "2024-05-23", "action_type_description": "ADMIN CHANGE", "amount_usd": -350385.14, "cumulative_obligated_usd": 18062486.86, "modification_description": "Deob excess funds"},
                            {"modification_number": "P00014", "action_type": "G", "action_date": "2025-11-14", "action_type_description": "EXERCISE OPTION", "amount_usd": 8369667.0, "cumulative_obligated_usd": 26432153.86, "modification_description": "Exercise option four"}
                        ]
                    },
                    "insights": {
                        "headline": "Clean burn story.",
                        "blocks": [
                            {
                                "id": "burn_posture",
                                "evidence": {"recommended_ptw_baseline_usd": 8388921.37, "pop_end_potential": "2026-12-15", "pop_end_current": "2023-11-20"}
                            },
                            {
                                "id": "award_story",
                                "summary": "FA805122F0001 is an IDIQ order against parent CONT_IDV_PARENT with four observed actions across base and options.",
                                "evidence": {}
                            }
                        ]
                    },
                    "vehicle_context": {"child_order_count": 22, "net_obligated_usd": 390322586.54},
                    "competitor_discovery": {"completeness_status": "high", "parent_vehicle_awardee_count": 8, "order_holder_count": 1},
                    "ptw_seed": {"recommended_baseline_usd": 8388921.37, "recent_annual_run_rate_usd": 8369667.0, "three_year_weighted_run_rate_usd": 8388921.37},
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
        assert brief.startswith("# FA805122F0001 Order Burn Brief")
        # BLUF prose, not raw bullets
        assert "**FA805122F0001** is best read as a single-order story" in brief
        assert "**$43.66M net** obligated across **4 transaction(s)**" in brief
        assert "burning **≈$8.38M/yr**" in brief
        assert "Parent vehicle: **CONT_IDV_PARENT** (8 awardees, high linkage)." in brief
        assert "Recommended PTW baseline: **$8.39M**" in brief
        # No raw Snapshot block any more
        assert "## Snapshot" not in brief
        # Burn Posture is Title Case + factual bullets
        assert "## Burn Posture" in brief
        assert "- Gross / Net Obligated: $44.07M / $43.66M (deobligations: -$350.4K across 1 action(s))" in brief
        assert "- Current Cadence: ≈$8.38M/year ($698.6K/month, $23.3K/day)" in brief
        assert "- Period of Performance: 2021-10-28 → 2023-11-20 (potential: 2026-12-15)" in brief
        assert "- Recommended PTW Baseline: $8.39M" in brief
        # Award Story has lead paragraph + ledger + mix + largest + fiscal trajectory
        assert "## Award Story & Key Inflection Points" in brief
        assert "FA805122F0001 is an IDIQ order against parent CONT_IDV_PARENT" in brief
        assert "- **Base** (2021-10-28, Initial Award): +$9.23M → cumulative $9.23M" in brief
        assert "- **P00005** (2022-11-17, Exercise Option): +$9.18M → cumulative $18.41M — Exercise option one" in brief
        assert "- **P00007** (2024-05-23, Admin Change): -$350.4K → cumulative $18.06M — Deob excess funds" in brief
        assert "- **P00014** (2025-11-14, Exercise Option): +$8.37M → cumulative $26.43M — Exercise option four" in brief
        assert "**Mix:**" in brief
        assert "**Largest single action:**" in brief
        assert "**Fiscal-year pattern:** FY22 $9.23M → FY23 $9.18M → FY24 -$350.4K → FY26 $8.37M." in brief
        # Inflection Points section is dropped for idiq_order (ledger covers it)
        assert "## Inflection Points" not in brief
        # Competitive context paragraph (not bullets)
        assert "## Competitive Context" in brief
        assert "Parent IDV **CONT_IDV_PARENT** has **8 awardees**" in brief
        assert "This order is the only observed holder under the current recipient slice." in brief
        # Caveats picks up deobligation auto-warning + recompete signal (current end < today < potential)
        assert "## Caveats" in brief
        assert "- Contains 1 deobligation action(s) totaling -$350.4K" in brief
        assert "- Current POP end (2023-11-20) is in the past while potential end is 2026-12-15" in brief
        # Manifest still uses descriptive labels
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

    assert "**PARENT-001** is best read as a parent IDV rollup" in brief
    assert "**$500.00 net** obligated across **2 transaction(s)**" in brief
    assert "## Burn Posture" in brief
    assert "- Gross / Net Obligated: $525.00 / $500.00 (deobligations: -$25.00 across 1 action(s))" in brief
    assert "- Recommended PTW Baseline: $500.00" in brief
    assert "## Award Story & Key Inflection Points" in brief
    assert "- **P00009** (2024-05-01, Other): -$25.00" in brief
    assert "- **P00012** (2024-09-01, Exercise Option): +$300.00" in brief
    assert "**Mix:**" in brief
    assert "## Competitive Context" in brief
    assert "Parent IDV CONT_IDV_PARENT has **2 awardees**" in brief
    assert "Awardees observed: HOLDCO B, HOLDCO A." in brief
    assert "## Caveats" in brief
    assert "- POP end dates inferred from modification timing." in brief
    assert "- Contains 1 deobligation action(s) totaling -$25.00" in brief
    # Old metric-dump bullets must be gone
    assert "- Quick read:" not in brief
    assert "- Burn snapshot:" not in brief
    assert "## Snapshot" not in brief
    assert "## Vehicle concentration" not in brief
    assert "Exact parent-awardee roster" not in brief


def test_build_competitive_intel_brief_markdown_uses_pop_segment_ledger() -> None:
    brief = build_competitive_intel_brief_markdown(
        {
            "input_contract_number": "FA805122F0001",
            "resolved": {"scenario": "idiq_order"},
            "obligations": {
                "total_obligated_usd": 18412872.0,
                "net_obligated_usd": 18412872.0,
                "rate_analysis": {"annual_burn_usd": 8382662.42, "monthly_burn_usd": 698555.2},
                "by_transaction": [
                    {"modification_number": "0", "action_date": "2021-10-28", "amount_usd": 9229200.0},
                    {"modification_number": "P00005", "action_date": "2022-11-17", "amount_usd": 9183672.0},
                ],
            },
            "insights": {
                "headline": "One order story.",
                "blocks": [
                    {
                        "id": "award_story",
                        "summary": "Two POP segments observed.",
                        "evidence": {
                            "period_of_performance_segments": [
                                {"label": "Base period", "pop_start_date": "2021-10-28", "pop_end_date": "2022-11-17", "months": 13.0, "obligated_usd": 9229200.0, "monthly_rate_usd": 709938.46},
                                {"label": "Option period 1", "pop_start_date": "2022-11-17", "pop_end_date": "2023-11-20", "months": 12.5, "obligated_usd": 9183672.0, "monthly_rate_usd": 734693.76},
                            ]
                        },
                    }
                ],
            },
            "warnings": [],
        },
        "Competitive Intel",
    )

    assert "## Award Story & Key Inflection Points" in brief
    assert "Two POP segments observed." in brief
    assert "- **Base period** (2021-10-28 → 2022-11-17, 13.0mo): $9.23M obligated at $709.9K/mo → cumulative $9.23M" in brief
    assert "- **Option period 1** (2022-11-17 → 2023-11-20, 12.5mo): $9.18M obligated at $734.7K/mo → cumulative $18.41M" in brief
    # POP-segment path skips per-mod Mix/Largest
    assert "**Mix:**" not in brief
    assert "**Largest single action:**" not in brief
    # No raw per-mod ledger lines
    assert "**Base** (2021-10-28" not in brief
    assert "**P00005** (2022-11-17" not in brief


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