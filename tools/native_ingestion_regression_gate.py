"""CLI for the native LightRAG ingestion regression gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.server.native_regression_gate import (  # noqa: E402
    build_native_ingestion_regression_report,
    format_report_text,
    write_report_json,
)


def _load_known_answer_checks(path: Path | None):
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        payload = payload.get("checks", [])
    if not isinstance(payload, list):
        raise ValueError("known-answer file must be a JSON list or an object with a 'checks' list")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the native LightRAG ingestion regression gate.")
    parser.add_argument("--workspace", type=Path, help="rag_storage/<workspace> path to inspect")
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Run the built-in no-GPU/no-MinerU smoke fixture. This is the default when --workspace is omitted.",
    )
    parser.add_argument("--known-answer-file", type=Path, help="JSON known-answer checks for workspace mode")
    parser.add_argument("--require-multimodal", action="store_true", help="Fail if no table evidence is found")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a text summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    known_answer_checks = _load_known_answer_checks(args.known_answer_file)
    use_fixture = args.fixture or args.workspace is None
    report = build_native_ingestion_regression_report(
        workspace_path=args.workspace,
        use_fixture=use_fixture,
        known_answer_checks=known_answer_checks,
        require_multimodal=args.require_multimodal,
    )
    if args.output:
        write_report_json(report, args.output)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_report_text(report), end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())