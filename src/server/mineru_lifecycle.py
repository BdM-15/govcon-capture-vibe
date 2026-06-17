"""MinerU local FastAPI subprocess lifecycle helpers.

Theseus's native LightRAG parser routes (`LIGHTRAG_PARSER=pdf:mineru-...`)
require MinerU's local FastAPI service to be reachable on
`MINERU_LOCAL_ENDPOINT` whenever `MINERU_API_MODE=local`. This module owns
the subprocess so `python app.py` is a single entry point.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, TextIO
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_DEFAULT_LOG_DIR = "logs"
_MINERU_FASTAPI_LOG_NAME = "mineru_fastapi.log"


def mineru_fastapi_log_path(log_dir: str | Path = _DEFAULT_LOG_DIR) -> Path:
    """Persistent MinerU subprocess log (survives terminal scrollback)."""
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / _MINERU_FASTAPI_LOG_NAME


def _read_log_tail(path: Path, *, max_chars: int = 1200) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-max_chars:]
    except OSError:
        return ""


@dataclass(frozen=True)
class MineruEndpoint:
    host: str
    port: int

    @property
    def docs_url(self) -> str:
        return f"http://{self.host}:{self.port}/docs"


def parse_mineru_endpoint(endpoint: str) -> MineruEndpoint:
    parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8888
    return MineruEndpoint(host=host, port=port)


def is_mineru_required(
    parser_rules: str | None,
    api_mode: str | None,
) -> bool:
    if not parser_rules or (api_mode or "").lower() != "local":
        return False
    return "mineru" in parser_rules.lower()


def is_port_listening(
    host: str,
    port: int,
    *,
    timeout: float = 0.5,
    socket_factory: Callable[[], socket.socket] | None = None,
) -> bool:
    factory = socket_factory or (lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    sock = factory()
    sock.settimeout(timeout)
    try:
        # 127.0.0.1 if host is "localhost" so we don't depend on AAAA records.
        target_host = "127.0.0.1" if host in {"localhost", "0.0.0.0"} else host
        sock.connect((target_host, port))
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


def wait_for_mineru(
    endpoint: MineruEndpoint,
    *,
    timeout: float = 180.0,
    interval: float = 1.0,
    url_opener: Callable[[str, float], object] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    opener = url_opener or (lambda url, to: urllib.request.urlopen(url, timeout=to))
    deadline = clock() + timeout
    while clock() < deadline:
        try:
            response = opener(endpoint.docs_url, 5.0)
            status = getattr(response, "status", None) or response.getcode()  # type: ignore[union-attr]
            close = getattr(response, "close", None)
            if callable(close):
                close()
            if status == 200:
                return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        sleep(interval)
    return False


@dataclass
class MineruController:
    endpoint: MineruEndpoint
    log_dir: str | Path = _DEFAULT_LOG_DIR
    process: subprocess.Popen | None = None
    _started_by_us: bool = False
    _output_log: TextIO | None = field(default=None, repr=False)

    @property
    def started_by_us(self) -> bool:
        return self._started_by_us

    @property
    def output_log_path(self) -> Path:
        return mineru_fastapi_log_path(self.log_dir)

    def _close_output_log(self) -> None:
        if self._output_log is not None:
            try:
                self._output_log.close()
            except OSError:
                pass
            self._output_log = None

    def start(
        self,
        *,
        python_executable: str | None = None,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
        port_check: Callable[[str, int], bool] = is_port_listening,
        wait: Callable[[MineruEndpoint], bool] = wait_for_mineru,
    ) -> bool:
        if port_check(self.endpoint.host, self.endpoint.port):
            logger.warning(
                "MinerU already listening on %s:%d (skip spawn). "
                "If parses fail with [Errno 22], stop the orphan on :%d and restart Theseus. "
                "Logs: %s",
                self.endpoint.host,
                self.endpoint.port,
                self.endpoint.port,
                self.output_log_path,
            )
            self._started_by_us = False
            return True

        executable = python_executable or sys.executable
        cmd = [
            executable,
            "-m",
            "mineru.cli.fast_api",
            "--host",
            self.endpoint.host,
            "--port",
            str(self.endpoint.port),
        ]
        child_env = os.environ.copy()
        child_env.setdefault("MINERU_API_DISABLE_ACCESS_LOG", "1")
        # MinerU/tqdm on Windows raises [Errno 22] when stdout is a PIPE (non-TTY).
        child_env.setdefault("PYTHONUNBUFFERED", "1")
        if sys.platform == "win32":
            child_env.setdefault("TQDM_DISABLE", "1")
        device_mode = str(child_env.get("MINERU_DEVICE_MODE", "cuda") or "cuda").strip()
        if device_mode:
            child_env["MINERU_DEVICE_MODE"] = device_mode
        cuda_devices = str(child_env.get("CUDA_VISIBLE_DEVICES", "") or "").strip()
        if cuda_devices:
            child_env["CUDA_VISIBLE_DEVICES"] = cuda_devices
        from src.server.engine_stack import log_mineru_stack_version

        stack_target = str(child_env.get("MINERU_STACK_VERSION", "3.3") or "3.3").strip()
        stack = log_mineru_stack_version(expected=stack_target, prefix="MinerU FastAPI spawn")
        log_path = self.output_log_path
        try:
            self._output_log = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
            self._output_log.write(
                f"\n--- MinerU FastAPI spawn {time.strftime('%Y-%m-%dT%H:%M:%S')} ---\n"
            )
            self._output_log.flush()
        except OSError as exc:
            logger.error("Failed to open MinerU output log %s: %s", log_path, exc)
            return False

        logger.info(
            "Starting MinerU FastAPI: %s (target=%s installed=v%s aligned=%s; "
            "MINERU_DEVICE_MODE=%s, CUDA_VISIBLE_DEVICES=%s; log=%s)",
            " ".join(cmd),
            stack.expected,
            stack.installed,
            stack.aligned,
            device_mode,
            cuda_devices or "(unset)",
            log_path,
        )
        try:
            # Redirect stderr to a real log file (not PIPE). PIPE breaks hybrid parse on Windows.
            self.process = popen(
                cmd,
                env=child_env,
                stdout=subprocess.DEVNULL,
                stderr=self._output_log,
            )
        except OSError as exc:
            logger.error("Failed to spawn MinerU FastAPI: %s", exc)
            self._close_output_log()
            return False

        self._started_by_us = True
        ready = wait(self.endpoint)
        if not ready:
            detail = _read_log_tail(log_path)
            logger.error(
                "MinerU did not become ready at %s within timeout (see %s)",
                self.endpoint.docs_url,
                log_path,
            )
            if detail:
                logger.error("MinerU log tail: %s", detail[-240:])
            self.stop()
            return False
        logger.info(
            "MinerU ready at %s (tail log: Get-Content %s -Wait -Tail 80)",
            self.endpoint.docs_url,
            log_path,
        )
        return True

    def stop(self, *, terminate_timeout: float = 10.0) -> None:
        proc = self.process
        if proc is not None and self._started_by_us:
            if proc.poll() is None:
                logger.info("Stopping MinerU FastAPI (pid=%s)", proc.pid)
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=terminate_timeout)
                    except subprocess.TimeoutExpired:
                        logger.warning("MinerU did not terminate; killing pid=%s", proc.pid)
                        proc.kill()
                        proc.wait(timeout=5.0)
                except OSError:
                    pass
            self.process = None
        self._close_output_log()


def build_controller_from_env(
    env: dict[str, str] | None = None,
) -> MineruController | None:
    source = env if env is not None else os.environ
    if not is_mineru_required(source.get("LIGHTRAG_PARSER"), source.get("MINERU_API_MODE")):
        return None
    endpoint = parse_mineru_endpoint(
        source.get("MINERU_LOCAL_ENDPOINT", "http://127.0.0.1:8888")
    )
    return MineruController(endpoint=endpoint)