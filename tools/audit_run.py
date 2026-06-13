#!/usr/bin/env python3
"""Print retrieval/deliverable forensics for a skill run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.skills.run_forensics import (  # noqa: E402
    build_run_forensics,
    format_run_forensics_report,
    write_run_forensics,
)


def _default_rag_root() -> Path:
    return ROOT / "rag_storage"


def resolve_run_dir(
    *,
    run_id: str,
    workspace: str,
    skill: str,
    rag_root: Path,
) -> Path:
    return rag_root / workspace / "skill_runs" / skill / run_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit a skill run's retrieval forensics.")
    parser.add_argument("run_id", help="Skill run id (folder name under skill_runs/<skill>/)")
    parser.add_argument(
        "--workspace",
        default="mcpp_rfp",
        help="Workspace name under rag_storage/ (default: mcpp_rfp)",
    )
    parser.add_argument(
        "--skill",
        default="mission-readiness-framer",
        help="Skill slug (default: mission-readiness-framer)",
    )
    parser.add_argument(
        "--rag-root",
        default=str(_default_rag_root()),
        help="Path to rag_storage root",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw retrieval_forensics.json payload",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write artifacts/retrieval_forensics.json before printing",
    )
    args = parser.parse_args(argv)

    run_dir = resolve_run_dir(
        run_id=args.run_id,
        workspace=args.workspace,
        skill=args.skill,
        rag_root=Path(args.rag_root),
    )
    if not run_dir.is_dir():
        print(f"Run directory not found: {run_dir}", file=sys.stderr)
        return 1

    payload = write_run_forensics(run_dir) if args.write else build_run_forensics(run_dir)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_run_forensics_report(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())