"""Re-merge upstream handoffs into an existing compiler run (offline repair)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.skills.mission_readiness_merge import (
    merge_upstream_handoffs,
    persist_normalized_compiler_frame,
    write_compiler_brief_scaffold,
)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python tools/remerge_mrf_compiler.py <compiler_run_dir>", file=sys.stderr)
        return 2

    run_dir = Path(sys.argv[1]).resolve()
    artifacts = run_dir / "artifacts"
    report_path = artifacts / "handoff_merge_report.json"
    if not report_path.is_file():
        print(f"Missing {report_path}", file=sys.stderr)
        return 1

    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = report.get("manifest") or []
    attached = [
        {
            "filename": item.get("filename"),
            "path": item.get("path"),
            "step_id": item.get("step_id"),
            "skill": item.get("skill"),
            "run_id": item.get("run_id"),
        }
        for item in manifest
        if isinstance(item, dict) and item.get("status") == "loaded"
    ]
    if not attached:
        print("No loaded handoffs in manifest", file=sys.stderr)
        return 1

    chain_ctx_path = artifacts / "chain_context.json"
    chain_ctx = {}
    if chain_ctx_path.is_file():
        loaded = json.loads(chain_ctx_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            chain_ctx = loaded

    merge_report = merge_upstream_handoffs(
        attached,
        run_dir,
        chain_step_context=chain_ctx.get("step_context") or {"role": "compiler"},
    )
    persist_normalized_compiler_frame(run_dir)
    write_compiler_brief_scaffold(run_dir)

    print(json.dumps(merge_report, indent=2))
    frame_path = artifacts / "mission_readiness_frame.json"
    frame = json.loads(frame_path.read_text(encoding="utf-8"))
    rows = frame.get("eval_crosswalk") or []
    filled = sum(
        1
        for row in rows
        if isinstance(row, dict) and str(row.get("readiness_link") or "").strip()
    )
    print(f"eval_crosswalk rows: {len(rows)}, readiness_link filled: {filled}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())