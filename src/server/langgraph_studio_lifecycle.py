"""LangGraph Studio subprocess lifecycle — single entry point with app.py."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse

from src.server.langsmith_runtime import langsmith_configured, langsmith_stats_payload
from src.server.mineru_lifecycle import is_port_listening
from src.server.runtime_state import get_langsmith_status

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class LangGraphStudioEndpoint:
    host: str
    port: int

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def graph_url(self) -> str:
        return studio_ui_url(self.url, graph_id="mission_readiness")


def studio_ui_url(api_url: str, *, graph_id: str = "mission_readiness") -> str:
    """LangGraph dev serves API locally; Studio UI is hosted on LangSmith."""
    base = quote(api_url, safe="")
    return f"https://smith.langchain.com/studio/?baseUrl={base}&graph={graph_id}"


def parse_studio_endpoint(port: int | str, host: str = "127.0.0.1") -> LangGraphStudioEndpoint:
    return LangGraphStudioEndpoint(host=host, port=int(port))


def is_auto_start_enabled(env: dict[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    raw = str(source.get("THESEUS_LANGGRAPH_STUDIO_AUTO_START", "true")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def langgraph_package_version() -> str | None:
    try:
        return version("langgraph")
    except PackageNotFoundError:
        return None


def _probe_studio_http(
    endpoint: LangGraphStudioEndpoint,
    *,
    url_opener: Callable[[str, float], object],
    timeout: float,
) -> bool:
    for path in ("/docs", "/ok", ""):
        try:
            response = url_opener(f"{endpoint.url}{path}", timeout)
            status = getattr(response, "status", None) or response.getcode()  # type: ignore[union-attr]
            close = getattr(response, "close", None)
            if callable(close):
                close()
            if status and int(status) < 500:
                return True
        except (urllib.error.URLError, ConnectionError, OSError, ValueError):
            continue
    return False


def wait_for_studio(
    endpoint: LangGraphStudioEndpoint,
    *,
    timeout: float = 120.0,
    interval: float = 1.0,
    url_opener: Callable[[str, float], object] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    process: subprocess.Popen | None = None,
    on_process_exit: Callable[[int, str], None] | None = None,
) -> bool:
    opener = url_opener or (lambda url, to: urllib.request.urlopen(url, timeout=to))
    deadline = clock() + timeout
    while clock() < deadline:
        if process is not None:
            return_code = process.poll()
            if return_code is not None:
                stderr_tail = ""
                stderr = getattr(process, "stderr", None)
                if stderr is not None and hasattr(stderr, "read"):
                    try:
                        stderr_tail = stderr.read()[-1200:]
                    except (OSError, ValueError):
                        stderr_tail = ""
                if on_process_exit is not None:
                    on_process_exit(int(return_code), stderr_tail)
                return False
        if _probe_studio_http(endpoint, url_opener=opener, timeout=5.0):
            return True
        sleep(interval)
    return False


def _studio_log_path(repo_root: Path) -> Path:
    log_dir = repo_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "langgraph_studio.log"


def _read_log_tail(path: Path, *, max_chars: int = 1200) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-max_chars:]
    except OSError:
        return ""


def fetch_studio_info(
    endpoint: LangGraphStudioEndpoint,
    *,
    url_opener: Callable[[str, float], object] | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    opener = url_opener or (lambda url, to: urllib.request.urlopen(url, timeout=to))
    try:
        response = opener(f"{endpoint.url}/info", timeout)
        raw = response.read()  # type: ignore[union-attr]
        close = getattr(response, "close", None)
        if callable(close):
            close()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except (urllib.error.URLError, ConnectionError, OSError, ValueError, json.JSONDecodeError):
        return {}


def studio_langsmith_enabled(
    info: dict[str, Any] | None = None,
    *,
    endpoint: LangGraphStudioEndpoint | None = None,
) -> bool:
    payload = info if info is not None else (
        fetch_studio_info(endpoint) if endpoint is not None else {}
    )
    flags = payload.get("flags")
    if not isinstance(flags, dict):
        return False
    return bool(flags.get("langsmith"))


def listener_pids_on_port(port: int, *, netstat_runner: Callable[..., Any] | None = None) -> list[int]:
    runner = netstat_runner or subprocess.run
    try:
        completed = runner(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return []
    pids: list[int] = []
    needle = f":{port}"
    for line in completed.stdout.splitlines():
        if "LISTENING" not in line.upper() or needle not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            pids.append(int(parts[-1]))
        except ValueError:
            continue
    return list(dict.fromkeys(pids))


def terminate_listeners_on_port(
    port: int,
    *,
    exclude_pid: int | None = None,
    kill: Callable[[int], None] | None = None,
    netstat_runner: Callable[..., Any] | None = None,
) -> list[int]:
    stopped: list[int] = []
    for pid in listener_pids_on_port(port, netstat_runner=netstat_runner):
        if pid <= 0 or pid == exclude_pid:
            continue
        try:
            if kill is None:
                completed = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F", "/T"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if completed.returncode != 0:
                    logger.warning(
                        "taskkill pid=%s on port %s failed: %s",
                        pid,
                        port,
                        (completed.stderr or completed.stdout or "").strip()[:160],
                    )
                    continue
            else:
                kill(pid)
            stopped.append(pid)
        except OSError:
            logger.warning("Failed to terminate pid=%s on port %s", pid, port)
    return stopped


def wait_for_port_free(
    host: str,
    port: int,
    *,
    timeout: float = 15.0,
    interval: float = 0.5,
    port_check: Callable[[str, int], bool] = is_port_listening,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    deadline = clock() + timeout
    while clock() < deadline:
        if not port_check(host, port):
            return True
        sleep(interval)
    return False


def _resolve_langgraph_command() -> list[str]:
    venv_exe = _REPO_ROOT / ".venv" / "Scripts" / "langgraph.exe"
    if venv_exe.is_file():
        return [str(venv_exe)]
    found = shutil.which("langgraph")
    if found:
        return [found]
    return [sys.executable, "-m", "langgraph_cli"]


@dataclass
class LangGraphStudioController:
    endpoint: LangGraphStudioEndpoint
    repo_root: Path = _REPO_ROOT
    process: subprocess.Popen | None = None
    _stderr_log: Any | None = None
    _started_by_us: bool = False
    _last_error: str | None = None

    @property
    def started_by_us(self) -> bool:
        return self._started_by_us

    def start(
        self,
        *,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
        port_check: Callable[[str, int], bool] = is_port_listening,
        wait: Callable[[LangGraphStudioEndpoint], bool] = wait_for_studio,
        command_builder: Callable[[], list[str]] | None = None,
    ) -> bool:
        if port_check(self.endpoint.host, self.endpoint.port):
            if wait(self.endpoint, timeout=5.0, interval=0.5):
                info = fetch_studio_info(self.endpoint)
                if langsmith_configured() and not studio_langsmith_enabled(info):
                    logger.warning(
                        "Recycling LangGraph Studio on %s — listener missing LANGSMITH_API_KEY",
                        self.endpoint.url,
                    )
                    terminate_listeners_on_port(
                        self.endpoint.port,
                        exclude_pid=os.getpid(),
                    )
                    if not wait_for_port_free(self.endpoint.host, self.endpoint.port):
                        self._last_error = (
                            f"port {self.endpoint.port} still in use after recycling Studio"
                        )
                        logger.error(self._last_error)
                        return False
                else:
                    logger.info(
                        "LangGraph Studio already listening on %s (skip spawn, langsmith=%s)",
                        self.endpoint.url,
                        studio_langsmith_enabled(info),
                    )
                    self._started_by_us = False
                    return True
            else:
                self._last_error = (
                    f"port {self.endpoint.port} is open but does not respond like LangGraph Studio"
                )
                logger.error(self._last_error)
                return False

        base_cmd = (command_builder or _resolve_langgraph_command)()
        cmd = [
            *base_cmd,
            "dev",
            "--host",
            self.endpoint.host,
            "--port",
            str(self.endpoint.port),
            "--no-browser",
            # Hot reload spawns a worker that imports langgraph_api.config before .env
            # is patched, so LANGSMITH_API_KEY is invisible and Studio shows the banner.
            "--no-reload",
            "--config",
            str(self.repo_root / "langgraph.json"),
        ]
        logger.info("Starting LangGraph Studio: %s", " ".join(cmd))
        log_path = _studio_log_path(self.repo_root)
        try:
            self._stderr_log = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
            self._stderr_log.write(
                f"\n--- LangGraph Studio spawn {time.strftime('%Y-%m-%dT%H:%M:%S')} ---\n"
            )
            self._stderr_log.flush()
            from src.server.langsmith_runtime import studio_subprocess_env

            self.process = popen(
                cmd,
                cwd=str(self.repo_root),
                stdout=subprocess.DEVNULL,
                stderr=self._stderr_log,
                env=studio_subprocess_env(),
            )
        except OSError as exc:
            self._last_error = str(exc)[:160]
            logger.error("Failed to spawn LangGraph Studio: %s", exc)
            return False

        self._started_by_us = True

        def _on_exit(code: int, stderr_tail: str) -> None:
            detail = stderr_tail.strip() or _read_log_tail(log_path)
            self._last_error = f"studio process exited ({code})"
            if detail:
                self._last_error = f"{self._last_error}: {detail[-240:]}"

        ready = wait(
            self.endpoint,
            process=self.process,
            on_process_exit=_on_exit,
        )
        if not ready:
            if not self._last_error:
                detail = _read_log_tail(log_path)
                self._last_error = "studio did not become ready within timeout"
                if detail:
                    self._last_error = f"{self._last_error} (see {log_path})"
            logger.error("LangGraph Studio not ready at %s", self.endpoint.url)
            self.stop()
            return False
        info = fetch_studio_info(self.endpoint)
        if langsmith_configured() and not studio_langsmith_enabled(info):
            self._last_error = (
                "studio started but /info reports langsmith=false — check LANGSMITH_API_KEY in .env"
            )
            logger.error(self._last_error)
            self.stop()
            return False
        logger.info(
            "LangGraph Studio ready at %s (langsmith=%s)",
            self.endpoint.graph_url,
            studio_langsmith_enabled(info),
        )
        return True

    def stop(self, *, terminate_timeout: float = 10.0) -> None:
        proc = self.process
        if proc is None or not self._started_by_us:
            return
        if proc.poll() is not None:
            self.process = None
            return
        logger.info("Stopping LangGraph Studio (pid=%s)", proc.pid)
        try:
            proc.terminate()
            try:
                proc.wait(timeout=terminate_timeout)
            except subprocess.TimeoutExpired:
                logger.warning("LangGraph Studio did not terminate; killing pid=%s", proc.pid)
                proc.kill()
                proc.wait(timeout=5.0)
        finally:
            self.process = None
            if self._stderr_log is not None:
                try:
                    self._stderr_log.close()
                except OSError:
                    pass
                self._stderr_log = None

    def status_payload(self) -> dict[str, Any]:
        ready = wait_for_studio(self.endpoint, timeout=3.0, interval=0.5)
        pkg_version = langgraph_package_version()
        langsmith = langsmith_stats_payload(get_langsmith_status())
        info = fetch_studio_info(self.endpoint) if ready else {}
        studio_tracing = studio_langsmith_enabled(info) if ready else False
        if ready and langsmith_configured() and not studio_tracing:
            ready = False
            if not self._last_error:
                self._last_error = "local studio missing LANGSMITH_API_KEY (recycle app to respawn)"
        if ready and not langsmith.get("ok"):
            ready = False
            if not self._last_error:
                self._last_error = langsmith.get("error") or "LangSmith not connected"
        return {
            "ok": ready,
            "state": "ready" if ready else "unavailable",
            "url": self.endpoint.url,
            "graph_url": self.endpoint.graph_url,
            "port": self.endpoint.port,
            "version": pkg_version,
            "orchestration": "langgraph",
            "langsmith": langsmith,
            "studio_langsmith_enabled": studio_tracing,
            "started_by_us": self._started_by_us,
            "error": None if ready else (self._last_error or "studio unreachable"),
        }


def build_controller_from_env(env: dict[str, str] | None = None) -> LangGraphStudioController | None:
    source = env if env is not None else os.environ
    if not is_auto_start_enabled(source):
        return None
    if langgraph_package_version() is None:
        logger.info("LangGraph not installed — skip Studio auto-start")
        return None
    if not langsmith_configured(source):
        logger.warning("LANGSMITH_API_KEY not set — LangGraph Studio requires LangSmith auth")
        return None
    explicit = str(source.get("THESEUS_LANGGRAPH_STUDIO_URL") or "").strip()
    if explicit:
        parsed = urlparse(explicit)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or int(str(source.get("LANGGRAPH_STUDIO_PORT") or "2024").strip())
        return LangGraphStudioController(endpoint=parse_studio_endpoint(port, host=host))
    port = int(str(source.get("LANGGRAPH_STUDIO_PORT") or "2024").strip())
    return LangGraphStudioController(endpoint=parse_studio_endpoint(port))


def studio_status_payload(status: dict[str, Any] | None) -> dict[str, Any]:
    if not status:
        return {
            "ok": False,
            "state": "unavailable",
            "url": "",
            "graph_url": "",
            "version": langgraph_package_version(),
            "orchestration": "langgraph",
            "error": "not started",
        }
    return {
        "ok": bool(status.get("ok")),
        "state": status.get("state") or ("ready" if status.get("ok") else "unavailable"),
        "url": status.get("url") or "",
        "graph_url": status.get("graph_url") or "",
        "version": status.get("version") or langgraph_package_version(),
        "orchestration": status.get("orchestration") or "langgraph",
        "started_by_us": bool(status.get("started_by_us")),
        "error": status.get("error"),
    }


def format_langgraph_banner_line(status: dict[str, Any] | None, colors: Any) -> str:
    pkg = langgraph_package_version() or "unknown"
    if not status or not status.get("ok"):
        err = (status or {}).get("error") or "studio offline"
        return (
            f"{colors.CYAN}v{pkg}{colors.RESET} in-process"
            f"  ·  Studio {colors.YELLOW}{err}{colors.RESET}"
        )
    url = status.get("graph_url") or status.get("url") or ""
    return (
        f"{colors.CYAN}v{pkg}{colors.RESET} in-process"
        f"  ·  Studio {colors.GREEN}{url}{colors.RESET}"
    )


def log_langgraph_studio_startup(status: dict[str, Any] | None, *, logger_obj: Any | None = None) -> None:
    log = logger_obj or logger
    if not status:
        log.info("LangGraph Studio status unavailable")
        return
    if status.get("ok"):
        log.info(
            "LangGraph Studio ready: %s (started_by_us=%s, version=%s)",
            status.get("graph_url"),
            status.get("started_by_us"),
            status.get("version"),
        )
        return
    log.warning(
        "LangGraph Studio unavailable: %s",
        status.get("error") or "unknown",
    )