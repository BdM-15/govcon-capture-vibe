"""E2E verify: restart server, invoke mission-readiness chain, assess artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.server.briefing_prompts import BRIEFING_PROMPT_LIBRARY
from src.skills.platform_step_finalize import _validate_compiler_run
from src.skills.readiness_solo_invoke import assess_readiness_solo_step

BASE = "http://127.0.0.1:9621"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
APP = ROOT / "app.py"
OUT = ROOT / "run-dir" / "chain_e2e_verify.json"
STEP_ORDER = [
    "workload",
    "eval",
    "pains",
    "modernization",
    "tea-leaves",
    "win-themes",
    "compile",
]


def _mission_prompt() -> str:
    return str(
        next(
            item
            for item in BRIEFING_PROMPT_LIBRARY
            if item.get("slice_id") == "mission-readiness"
        )["prompt"]
    )


def _kill_server() -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "$p=(Get-NetTCPConnection -LocalPort 9621 -EA SilentlyContinue | "
                "Select-Object -ExpandProperty OwningProcess -Unique | "
                "Where-Object { $_ -gt 0 }); "
                "if ($p) { $p | ForEach-Object { Stop-Process -Id $_ -Force -EA SilentlyContinue } }"
            ),
        ],
        check=False,
        capture_output=True,
    )
    time.sleep(2)


def _start_server() -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [str(PYTHON), str(APP)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_health(*, timeout_s: float = 120.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=5.0) as client:
                if client.get(f"{BASE}/health").status_code == 200:
                    return True
        except httpx.HTTPError:
            pass
        time.sleep(2)
    return False


def _invoke_chain() -> tuple[float, dict]:
    payload = {
        "preset": "mission-readiness",
        "name": "mission-readiness-chain",
        "prompt": _mission_prompt(),
        "user_addendum": "",
    }
    t0 = time.time()
    with httpx.Client(timeout=7200.0) as client:
        response = client.post(f"{BASE}/api/ui/skill-chains/invoke", json=payload)
    wall = time.time() - t0
    if response.status_code >= 400:
        raise RuntimeError(f"invoke failed {response.status_code}: {response.text[:2000]}")
    body = response.json()
    return wall, body


def _workspace_root() -> Path:
    from src.core import get_settings

    return ROOT / "rag_storage" / get_settings().workspace


def assess_chain(chain: dict) -> dict:
    steps = chain.get("steps") or {}
    report: dict = {"steps": {}, "failed": [], "skipped": [], "verdict": "FAIL"}

    for step_id in STEP_ORDER:
        step = steps.get(step_id) or {}
        run_dir = str(step.get("run_dir") or "").strip()
        status = str(step.get("status") or "")
        error = str(step.get("error") or "")
        elapsed_s = round((step.get("elapsed_ms") or 0) / 1000, 1)
        entry: dict = {"status": status, "elapsed_s": elapsed_s, "error": error[:300]}
        if run_dir:
            entry["run_dir"] = run_dir
            path = Path(run_dir)
            if step_id == "compile" and path.is_dir():
                gate = _validate_compiler_run(path)
                entry["compiler_gate"] = gate[:6]
                entry["artifacts"] = {
                    name: (path / "artifacts" / name).is_file()
                    for name in (
                        "mission_readiness_frame.json",
                        "brief.md",
                        "mission_readiness_frame_brief.docx",
                    )
                }
                if (path / "artifacts" / "mission_readiness_frame.json").is_file():
                    frame = json.loads(
                        (path / "artifacts" / "mission_readiness_frame.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    entry["eval_crosswalk_rows"] = len(frame.get("eval_crosswalk") or [])
                    entry["brief_chars"] = len(
                        (path / "artifacts" / "brief.md").read_text(encoding="utf-8")
                    )
            elif step_id != "compile" and path.is_dir():
                solo = assess_readiness_solo_step(
                    step_id=step_id,
                    run_dir=path,
                    workspace_root=_workspace_root(),
                )
                entry["solo_gate_passed"] = solo.passed
                entry["solo_errors"] = solo.errors[:4]
        report["steps"][step_id] = entry
        if status == "failed":
            report["failed"].append(step_id)
        if status == "skipped" and error:
            report["skipped"].append(step_id)

    compile = report["steps"].get("compile") or {}
    chain_status = str(chain.get("status") or "")
    compile_ok = (
        compile.get("status") == "completed"
        and (compile.get("artifacts") or {}).get("mission_readiness_frame.json")
        and (compile.get("artifacts") or {}).get("brief.md")
        and not compile.get("compiler_gate")
    )
    if (
        chain_status in ("completed", "partial")
        and not report["failed"]
        and not report["skipped"]
        and compile_ok
    ):
        report["verdict"] = "PASS"
    return report


def main() -> int:
    proc: subprocess.Popen[bytes] | None = None
    try:
        print("kill_server", flush=True)
        _kill_server()
        print("start_server", flush=True)
        proc = _start_server()
        if not _wait_health():
            print("ERROR: server health timeout", flush=True)
            return 2
        print("health_ok", flush=True)

        wall, body = _invoke_chain()
        chain = body.get("chain") or {}
        report = assess_chain(chain)
        report["wall_seconds"] = round(wall, 1)
        report["wall_minutes"] = round(wall / 60, 1)
        report["chain_id"] = chain.get("chain_id")
        report["chain_status"] = chain.get("status")
        report["chain_error"] = str(chain.get("error") or "")[:500]

        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps({"report": report, "chain": chain}, indent=2),
            encoding="utf-8",
        )

        print(json.dumps(report, indent=2), flush=True)
        return 0 if report["verdict"] == "PASS" else 1
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        _kill_server()


if __name__ == "__main__":
    raise SystemExit(main())