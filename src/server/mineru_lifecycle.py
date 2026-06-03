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
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


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
    process: subprocess.Popen | None = None
    _started_by_us: bool = False

    @property
    def started_by_us(self) -> bool:
        return self._started_by_us

    def start(
        self,
        *,
        python_executable: str | None = None,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
        port_check: Callable[[str, int], bool] = is_port_listening,
        wait: Callable[[MineruEndpoint], bool] = wait_for_mineru,
    ) -> bool:
        if port_check(self.endpoint.host, self.endpoint.port):
            logger.info(
                "MinerU already listening on %s:%d (skip spawn)",
                self.endpoint.host,
                self.endpoint.port,
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
        logger.info("Starting MinerU FastAPI: %s", " ".join(cmd))
        self.process = popen(cmd)
        self._started_by_us = True
        ready = wait(self.endpoint)
        if not ready:
            logger.error(
                "MinerU did not become ready at %s within timeout", self.endpoint.docs_url
            )
            self.stop()
            return False
        logger.info("MinerU ready at %s", self.endpoint.docs_url)
        return True

    def stop(self, *, terminate_timeout: float = 10.0) -> None:
        proc = self.process
        if proc is None or not self._started_by_us:
            return
        if proc.poll() is not None:
            self.process = None
            return
        logger.info("Stopping MinerU FastAPI (pid=%s)", proc.pid)
        try:
            proc.terminate()
            try:
                proc.wait(timeout=terminate_timeout)
            except subprocess.TimeoutExpired:
                logger.warning("MinerU did not terminate; killing pid=%s", proc.pid)
                proc.kill()
                proc.wait(timeout=5.0)
        finally:
            self.process = None


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
