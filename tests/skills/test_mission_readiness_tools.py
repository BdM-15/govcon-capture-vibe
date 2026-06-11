"""Tests for mission-readiness-framer deterministic helpers."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.skill_local_tools import load_skill_tool_module


def _helpers():
    skill_dir = Path(__file__).resolve().parents[2] / ".github" / "skills" / "mission-readiness-framer"
    return load_skill_tool_module(skill_dir, "mission_readiness_tools")


def test_detect_capability_overlay_request_finds_vendor_and_url() -> None:
    helpers = _helpers()
    overlay = helpers.detect_capability_overlay_request(
        "Can Tagup, Inc with their Manifest platform help? Review: https://tagup.ai/platform"
    )
    assert overlay is not None
    assert "tagup.ai/platform" in overlay["urls"][0]
    assert "Tagup" in overlay["vendor"]


def test_validate_mission_readiness_run_flags_thin_crosswalk_and_overlay(tmp_path: Path) -> None:
    helpers = _helpers()
    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "brief.md").write_text("# Brief\n\n## Eval cross-walk\n\n| a | b |\n", encoding="utf-8")
    (artifacts / "mission_readiness_frame.json").write_text(
        json.dumps(
            {
                "customer_pain_points": [{"id": "PP-001"}],
                "eval_crosswalk": [
                    {
                        "evaluation_factor": "Technical",
                        "pws_clusters": ["PWS 3"],
                        "readiness_link": "too short",
                        "proof_expected": "x",
                        "source_chunk_ids": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    issues = helpers.validate_mission_readiness_run(
        run_dir,
        user_prompt="Review https://tagup.ai/platform for Tagup, Inc applicability",
    )

    assert any("brief.md too short" in issue for issue in issues)
    assert any("eval_crosswalk row 1 readiness_link too thin" in issue for issue in issues)
    assert any("capability_overlay is missing" in issue for issue in issues)
    assert any("Capability overlay section too thin" in issue for issue in issues)

    audit_path = helpers.write_depth_audit(run_dir, issues)
    assert audit_path.is_file()
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["issue_count"] == len(issues)