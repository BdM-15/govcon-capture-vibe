"""Quick qualitative assessment of a mission-readiness-framer compile run."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.skills.readiness_content_gates import (
    claim_gaps_brief_issues,
    is_boilerplate_text,
    substance_issues_for_crosswalk,
    tail_compression_issues_for_brief,
)
from src.skills.skill_local_tools import load_skill_tool_module


def assess(run_dir: Path) -> dict:
    artifacts = run_dir / "artifacts"
    frame_path = artifacts / "mission_readiness_frame.json"
    brief_path = artifacts / "brief.md"
    depth_path = artifacts / "depth_audit.json"

    payload = json.loads(frame_path.read_text(encoding="utf-8"))
    brief = brief_path.read_text(encoding="utf-8", errors="replace")

    crosswalk = payload.get("eval_crosswalk") or []
    claim_gaps = payload.get("claim_gaps") or []
    overlay = payload.get("capability_overlay")

    invalid_chunks = []
    for index, row in enumerate(crosswalk, start=1):
        if not isinstance(row, dict):
            continue
        for chunk_id in row.get("source_chunk_ids") or []:
            text = str(chunk_id)
            if not re.match(r"^(?:doc-|chunk-|tb-)", text, re.I):
                invalid_chunks.append((index, text))

    helpers = load_skill_tool_module(
        ROOT / ".github" / "skills" / "mission-readiness-framer",
        "mission_readiness_tools",
    )
    validate_issues = helpers.validate_mission_readiness_run(run_dir, user_prompt="")

    sections = []
    for line in brief.splitlines():
        if line.startswith("## "):
            sections.append(line[3:].strip())

    return {
        "run_dir": str(run_dir),
        "brief_chars": len(brief),
        "brief_lines": len(brief.splitlines()),
        "sections": sections,
        "eval_rows": len(crosswalk),
        "claim_gaps_count": len(claim_gaps),
        "has_overlay": overlay is not None,
        "invalid_chunk_ids": invalid_chunks[:8],
        "boilerplate_rows": sum(
            1
            for row in crosswalk
            if isinstance(row, dict)
            and (
                is_boilerplate_text(str(row.get("readiness_link") or ""))
                or is_boilerplate_text(str(row.get("proof_expected") or ""))
            )
        ),
        "gate_crosswalk_issues": substance_issues_for_crosswalk(crosswalk)[:10],
        "gate_tail_issues": tail_compression_issues_for_brief(brief),
        "gate_claim_gap_issues": claim_gaps_brief_issues(payload, brief),
        "validate_issues": validate_issues[:15],
        "validate_issue_count": len(validate_issues),
        "depth_audit": json.loads(depth_path.read_text(encoding="utf-8"))
        if depth_path.is_file()
        else {},
    }


def main() -> int:
    run_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    base = ROOT / "rag_storage" / "mcpp_rfp" / "skill_runs" / "mission-readiness-framer"
    if run_arg:
        candidate = Path(run_arg)
        run_dir = candidate if candidate.is_dir() else base / run_arg
    else:
        run_dir = sorted(base.iterdir(), key=lambda p: p.name)[-1]
    report = assess(run_dir)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())