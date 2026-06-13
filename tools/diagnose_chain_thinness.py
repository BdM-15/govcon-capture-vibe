"""Evidence-based comparison: monolith vs chain micro-skills vs compile."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT / "rag_storage" / "mcpp_rfp"
CHAIN_ID = "20260612_203820_mission_readiness_chain"
MONOLITH = WS / "skill_runs/mission-readiness-framer/20260612_180545_build_the_mission_readiness_fram"
COMPILE = WS / "skill_runs/mission-readiness-framer/20260612_204515_build_the_mission_readiness_fram"
CHAIN = WS / f"skill_chains/{CHAIN_ID}"

MICRO_SKILLS = [
    "readiness-frame-eval",
    "readiness-frame-workload",
    "readiness-frame-pains",
    "readiness-frame-modernization",
    "readiness-frame-tea-leaves",
    "readiness-frame-win-themes",
]

HANDOFF_FILES = {
    "readiness-frame-eval": "eval_handoff.json",
    "readiness-frame-workload": "workload_handoff.json",
    "readiness-frame-pains": "pains_handoff.json",
    "readiness-frame-modernization": "modernization_handoff.json",
    "readiness-frame-tea-leaves": "tea_leaves_handoff.json",
    "readiness-frame-win-themes": "win_themes_handoff.json",
}


def _load_json(path: Path) -> dict | list | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _run_stats(run_dir: Path) -> dict:
    artifacts = run_dir / "artifacts"
    frame = _load_json(artifacts / "mission_readiness_frame.json") or {}
    scratch = artifacts / "research_scratchpad.md"
    brief = artifacts / "brief.md"
    harness = _load_json(artifacts / "harness_state.json") or {}
    transcript = _load_json(run_dir / "transcript.json") or []
    depth = _load_json(artifacts / "depth_audit.json") or {}

    tool_counts: dict[str, int] = {}
    for entry in transcript if isinstance(transcript, list) else []:
        if isinstance(entry, dict) and entry.get("kind") == "tool":
            name = str(entry.get("name") or "")
            tool_counts[name] = tool_counts.get(name, 0) + 1

    run_md = (run_dir / "run.md").read_text(encoding="utf-8", errors="replace") if (run_dir / "run.md").is_file() else ""
    turns = re.search(r"^turns:\s*(\d+)", run_md, re.M)
    finish = re.search(r"^finish_reason:\s*(\S+)", run_md, re.M)
    elapsed = re.search(r"^elapsed_ms:\s*(\d+)", run_md, re.M)

    array_keys = [
        "eval_crosswalk",
        "customer_pain_points",
        "verbatim_extracts",
        "win_theme_candidates",
        "importance_signals",
        "implicit_criteria",
        "current_methods",
        "innovation_opportunities",
        "claim_gaps",
    ]
    counts = {key: len(frame.get(key) or []) if isinstance(frame, dict) else 0 for key in array_keys}

    return {
        "scratchpad_chars": len(scratch.read_text(encoding="utf-8", errors="replace")) if scratch.is_file() else 0,
        "brief_chars": len(brief.read_text(encoding="utf-8", errors="replace")) if brief.is_file() else 0,
        "harness_scratchpad_chars": int(harness.get("scratchpad_chars") or 0),
        "turns": int(turns.group(1)) if turns else None,
        "finish_reason": finish.group(1) if finish else None,
        "elapsed_ms": int(elapsed.group(1)) if elapsed else None,
        "tool_counts": tool_counts,
        "depth_audit": depth,
        "frame_counts": counts,
    }


def _handoff_stats(skill: str, run_dir: Path) -> dict:
    handoff_name = HANDOFF_FILES[skill]
    handoff_path = run_dir / "artifacts" / handoff_name
    brief_path = run_dir / "artifacts" / "brief.md"
    scratch_path = run_dir / "artifacts" / "research_scratchpad.md"
    payload = _load_json(handoff_path)
    run_md = (run_dir / "run.md").read_text(encoding="utf-8", errors="replace") if (run_dir / "run.md").is_file() else ""
    finish = re.search(r"^finish_reason:\s*(\S+)", run_md, re.M)
    turns = re.search(r"^turns:\s*(\d+)", run_md, re.M)

    row_counts: dict[str, int] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, list):
                row_counts[key] = len(value)

    eval_rows = 0
    if isinstance(payload, dict):
        crosswalk = payload.get("eval_crosswalk")
        if isinstance(crosswalk, list):
            eval_rows = len(crosswalk)
        # alternate schema from synthesis
        if not eval_rows and "factors" in payload:
            eval_rows = len(payload.get("factors") or [])

    return {
        "run_dir": str(run_dir.name),
        "handoff_file": handoff_name,
        "handoff_bytes": handoff_path.stat().st_size if handoff_path.is_file() else 0,
        "handoff_keys": list(payload.keys()) if isinstance(payload, dict) else [],
        "handoff_row_counts": row_counts,
        "eval_crosswalk_rows": eval_rows,
        "brief_chars": len(brief_path.read_text(encoding="utf-8", errors="replace")) if brief_path.is_file() else 0,
        "scratchpad_chars": len(scratch_path.read_text(encoding="utf-8", errors="replace")) if scratch_path.is_file() else 0,
        "finish_reason": finish.group(1) if finish else None,
        "turns": int(turns.group(1)) if turns else None,
        "handoff_sample_keys": list((payload or {}).keys())[:12] if isinstance(payload, dict) else [],
    }


def _compile_handoff_usage() -> dict:
    run_md = (COMPILE / "run.md").read_text(encoding="utf-8", errors="replace")
    transcript = _load_json(COMPILE / "transcript.json") or []

    # Extract input_artifacts from chain handoff block in prompt
    input_artifacts: list[dict] = []
    match = re.search(r"## Theseus Chain Handoff\n```json\n(.*?)\n```", run_md, re.S)
    if match:
        handoff = json.loads(match.group(1))
        input_artifacts = handoff.get("input_artifacts") or []

    read_file_targets: list[str] = []
    write_file_targets: list[str] = []
    for entry in transcript if isinstance(transcript, list) else []:
        if not isinstance(entry, dict) or entry.get("kind") != "tool":
            continue
        name = str(entry.get("name") or "")
        args_raw = entry.get("arguments") or "{}"
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except json.JSONDecodeError:
            args = {}
        path = str(args.get("path") or "")
        if name == "read_file" and path:
            read_file_targets.append(path.replace("\\", "/").split("/")[-1])
        if name == "write_file" and path:
            write_file_targets.append(path.replace("\\", "/").split("/")[-1])

    handoff_reads = [p for p in read_file_targets if "handoff" in p.lower()]
    return {
        "input_artifact_count": len(input_artifacts),
        "input_artifact_filenames": [a.get("filename") for a in input_artifacts],
        "input_artifact_handoffs": [
            a.get("filename") for a in input_artifacts if "handoff" in str(a.get("filename") or "").lower()
        ],
        "read_file_count": len(read_file_targets),
        "read_file_unique": sorted(set(read_file_targets)),
        "handoff_files_read": sorted(set(handoff_reads)),
        "write_file_targets": sorted(set(write_file_targets)),
    }


def main() -> None:
    chain = _load_json(CHAIN / "chain.json") or {}
    steps = chain.get("steps") or {}

    print("=== MONOLITH vs COMPILE ===")
    mono = _run_stats(MONOLITH)
    comp = _run_stats(COMPILE)
    print(json.dumps({"monolith": mono, "compile": comp}, indent=2))

    print("\n=== MICRO-SKILL HANDOFFS ===")
    micro_report = []
    for skill in MICRO_SKILLS:
        step = steps.get(skill.split("readiness-frame-")[-1].replace("eval", "eval") if False else None)
        # find step by skill name
        run_info = None
        for step_id, info in steps.items():
            if isinstance(info, dict) and info.get("skill") == skill:
                run_info = info
                break
        if not run_info:
            # step keys are eval, workload, etc.
            key_map = {
                "readiness-frame-eval": "eval",
                "readiness-frame-workload": "workload",
                "readiness-frame-pains": "pains",
                "readiness-frame-modernization": "modernization",
                "readiness-frame-tea-leaves": "tea-leaves",
                "readiness-frame-win-themes": "win-themes",
            }
            run_info = steps.get(key_map[skill], {})
        run_dir = Path(str(run_info.get("run_dir") or ""))
        if not run_dir.is_dir():
            # fallback: latest run for skill
            base = WS / "skill_runs" / skill
            runs = sorted(base.glob("20260612_*"), key=lambda p: p.name)
            run_dir = runs[-1] if runs else base
        micro_report.append({"skill": skill, "status": run_info.get("status"), **_handoff_stats(skill, run_dir)})
    print(json.dumps(micro_report, indent=2))

    print("\n=== COMPILE HANDOFF USAGE ===")
    print(json.dumps(_compile_handoff_usage(), indent=2))

    # eval handoff schema sample
    eval_run = Path(steps.get("eval", {}).get("run_dir", ""))
    if eval_run.is_dir():
        payload = _load_json(eval_run / "artifacts" / "eval_handoff.json")
        if isinstance(payload, dict):
            cw = payload.get("eval_crosswalk")
            sample = cw[0] if isinstance(cw, list) and cw else payload
            print("\n=== EVAL HANDOFF SCHEMA SAMPLE ===")
            print(json.dumps(sample, indent=2)[:2000])


if __name__ == "__main__":
    main()