"""Tests for mission-readiness-framer workbook shaping."""

from __future__ import annotations

import json
from pathlib import Path

from src.skills.skill_local_tools import load_skill_tool_module

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MRF_DIR = _REPO_ROOT / ".github" / "skills" / "mission-readiness-framer"
_tools = load_skill_tool_module(_MRF_DIR, "mission_readiness_tools")


def test_build_workbook_payload_includes_frame_summary() -> None:
    payload = _tools.build_workbook_payload(
        {
            "opportunity_context": {"solicitation_id": "ABC-123", "agency": "USMC"},
            "mission_readiness_frame": {
                "readiness_outcome": "Sustain FMC",
                "confidence": "high",
                "our_read": "Contract instruments readiness.",
                "failure_modes_feared": ["surge gap"],
                "workload_enablers": [{"label": "Maintenance", "readiness_link": "FMC"}],
                "readiness_signals": [{"signal": "crisis", "type": "explicit"}],
                "source_chunk_ids": ["chunk-001"],
            },
            "customer_pain_points": [{"id": "PP-001", "text": "pain"}],
            "verbatim_extracts": [{"id": "VE-001", "quote": "shall perform"}],
            "eval_crosswalk": [{"evaluation_factor": "Technical"}],
        }
    )

    assert payload["frame_summary"][0]["solicitation_id"] == "ABC-123"
    assert payload["frame_summary"][0]["readiness_outcome"] == "Sustain FMC"
    assert payload["workload_enablers"][0]["label"] == "Maintenance"
    assert payload["verbatim_extracts"][0]["quote"] == "shall perform"


def test_write_workbook_source_writes_flattened_json(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    envelope = {
        "mission_readiness_frame": {"readiness_outcome": "Ready"},
        "customer_pain_points": [],
    }
    (artifacts / "mission_readiness_frame.json").write_text(
        json.dumps(envelope), encoding="utf-8"
    )

    out = _tools.write_workbook_source(artifacts, envelope)
    assert out is not None
    shaped = json.loads(out.read_text(encoding="utf-8"))
    assert "frame_summary" in shaped
    assert shaped["frame_summary"][0]["readiness_outcome"] == "Ready"