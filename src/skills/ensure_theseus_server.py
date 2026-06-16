"""Ensure Theseus API server is up and running current readiness gate code."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.skills.server_code_fingerprint import compute_server_code_fingerprint
_DEFAULT_BASE = "http://127.0.0.1:9621"
_PYTHON = _REPO_ROOT / ".venv" / "Scripts" / "python.exe"
_APP = _REPO_ROOT / "app.py"


def kill_server_on_port(port: int = 9621) -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                f"$p=(Get-NetTCPConnection -LocalPort {port} -EA SilentlyContinue | "
                "Select-Object -ExpandProperty OwningProcess -Unique | "
                "Where-Object { $_ -gt 0 }); "
                "if ($p) { $p | ForEach-Object { Stop-Process -Id $_ -Force -EA SilentlyContinue } }"
            ),
        ],
        check=False,
        capture_output=True,
    )
    time.sleep(2)


def _port_is_listening(port: int = 9621) -> bool:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                f"(Get-NetTCPConnection -LocalPort {port} -State Listen -EA SilentlyContinue | "
                "Measure-Object).Count -gt 0"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout or "").strip().lower() == "true"


def start_server_background(*, repo_root: Path | None = None) -> None:
    """Start app.py detached so the launcher process can exit without killing the server."""
    root = repo_root or _REPO_ROOT
    python = root / ".venv" / "Scripts" / "python.exe"
    app = root / "app.py"
    log_dir = root / "run-dir"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = log_dir / "server_stdout.log"
    stderr_log = log_dir / "server_stderr.log"
    if sys.platform == "win32":
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    f"Start-Process -FilePath '{python}' "
                    f"-ArgumentList '{app}' "
                    f"-WorkingDirectory '{root}' "
                    "-WindowStyle Hidden "
                    f"-RedirectStandardOutput '{stdout_log}' "
                    f"-RedirectStandardError '{stderr_log}'"
                ),
            ],
            check=False,
            capture_output=True,
        )
        return
    subprocess.Popen(
        [str(python), str(app)],
        cwd=str(root),
        stdout=open(stdout_log, "ab"),  # noqa: SIM115
        stderr=open(stderr_log, "ab"),  # noqa: SIM115
        start_new_session=True,
        stdin=subprocess.DEVNULL,
    )


def fetch_server_fingerprint(
    base_url: str = _DEFAULT_BASE,
    *,
    timeout_s: float = 5.0,
) -> str | None:
    url = f"{base_url.rstrip('/')}/api/ui/server-info"
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.get(url)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    fingerprint = str(body.get("code_fingerprint") or "").strip()
    return fingerprint or None


def wait_for_fresh_server(
    expected_fingerprint: str,
    *,
    base_url: str = _DEFAULT_BASE,
    timeout_s: float = 180.0,
    poll_s: float = 2.0,
) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if fetch_server_fingerprint(base_url) == expected_fingerprint:
            return True
        time.sleep(poll_s)
    return False


def ensure_theseus_server_fresh(
    *,
    base_url: str = _DEFAULT_BASE,
    repo_root: Path | None = None,
    restart: bool = True,
    startup_timeout_s: float = 180.0,
) -> tuple[bool, str]:
    """Return (ok, message). Restarts server when fingerprint missing or stale."""
    root = repo_root or _REPO_ROOT
    expected = compute_server_code_fingerprint(repo_root=root)
    live = fetch_server_fingerprint(base_url)
    if live == expected:
        return True, f"server fresh (fingerprint={expected})"

    if live is None and not restart:
        return False, "server down and restart disabled — start app.py first"

    if live is not None and live != expected and not restart:
        return (
            False,
            f"server stale (live={live}, expected={expected}) — restart app.py or rerun without --skip-server-ensure",
        )

    kill_server_on_port(9621)
    if not _PYTHON.is_file() or not _APP.is_file():
        return False, f"missing runtime ({_PYTHON} or {_APP})"

    start_server_background(repo_root=root)
    if wait_for_fresh_server(expected, base_url=base_url, timeout_s=startup_timeout_s):
        time.sleep(2.0)
        if (
            fetch_server_fingerprint(base_url) == expected
            and _port_is_listening(9621)
        ):
            return True, f"server restarted fresh (fingerprint={expected})"
        return False, "server matched fingerprint then died — see run-dir/server_stderr.log"
    return False, f"server restart timeout — expected fingerprint {expected}"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=_DEFAULT_BASE)
    parser.add_argument("--no-restart", action="store_true")
    parser.add_argument("--kill-only", action="store_true")
    args = parser.parse_args(argv)

    if args.kill_only:
        kill_server_on_port()
        print("killed port 9621", flush=True)
        return 0

    ok, message = ensure_theseus_server_fresh(
        base_url=args.base_url,
        restart=not args.no_restart,
    )
    print(message, flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())