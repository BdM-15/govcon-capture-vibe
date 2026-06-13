"""LangSmith tracing + Studio auth env for LangGraph subprocesses."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable

from dotenv import dotenv_values

logger = logging.getLogger(__name__)

# Vars LangGraph dev and LangChain tracing read (langgraph.json loads .env too).
LANGSMITH_ENV_KEYS: tuple[str, ...] = (
    "LANGSMITH_API_KEY",
    "LANGCHAIN_API_KEY",
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_PROJECT",
    "LANGCHAIN_PROJECT",
    "LANGSMITH_ENDPOINT",
    "LANGCHAIN_ENDPOINT",
    "LANGSMITH_WORKSPACE_ID",
)


def _truthy(raw: str | None, *, default: bool = True) -> bool:
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def apply_langsmith_env(
    target: dict[str, str] | None = None,
    *,
    source: dict[str, str] | None = None,
) -> dict[str, str]:
    """Normalize LangSmith/LangChain aliases into *target* (defaults: os.environ)."""
    env = os.environ if target is None else target
    src = os.environ if source is None else source

    api_key = str(src.get("LANGSMITH_API_KEY") or src.get("LANGCHAIN_API_KEY") or "").strip()
    if api_key:
        env["LANGSMITH_API_KEY"] = api_key
        env.setdefault("LANGCHAIN_API_KEY", api_key)

    project = str(
        src.get("LANGSMITH_PROJECT") or src.get("LANGCHAIN_PROJECT") or "theseus-mission-readiness"
    ).strip()
    if project:
        env["LANGSMITH_PROJECT"] = project
        env.setdefault("LANGCHAIN_PROJECT", project)

    if _truthy(src.get("LANGSMITH_TRACING"), default=True):
        env["LANGSMITH_TRACING"] = "true"
    else:
        env["LANGSMITH_TRACING"] = "false"

    tracing_on = _truthy(src.get("LANGCHAIN_TRACING_V2"), default=_truthy(env.get("LANGSMITH_TRACING")))
    if tracing_on:
        env["LANGCHAIN_TRACING_V2"] = "true"
        env["LANGSMITH_TRACING_V2"] = "true"
    else:
        env["LANGCHAIN_TRACING_V2"] = "false"
        env["LANGSMITH_TRACING_V2"] = "false"

    endpoint = str(src.get("LANGSMITH_ENDPOINT") or src.get("LANGCHAIN_ENDPOINT") or "").strip()
    if endpoint:
        env["LANGSMITH_ENDPOINT"] = endpoint
        env.setdefault("LANGCHAIN_ENDPOINT", endpoint)

    workspace_id = str(src.get("LANGSMITH_WORKSPACE_ID") or "").strip()
    if workspace_id:
        env["LANGSMITH_WORKSPACE_ID"] = workspace_id

    return env


def langsmith_configured(env: dict[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    return bool(str(source.get("LANGSMITH_API_KEY") or source.get("LANGCHAIN_API_KEY") or "").strip())


def verify_langsmith_connection(
    *,
    env: dict[str, str] | None = None,
    client_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Ping LangSmith with the configured API key (no trace upload)."""
    scoped = dict(os.environ if env is None else env)
    apply_langsmith_env(scoped, source=scoped)
    api_key = str(scoped.get("LANGSMITH_API_KEY") or "").strip()
    project = str(scoped.get("LANGSMITH_PROJECT") or "theseus-mission-readiness").strip()
    tracing = _truthy(scoped.get("LANGSMITH_TRACING"), default=True)

    if not api_key:
        return {
            "ok": False,
            "state": "unconfigured",
            "project": project,
            "tracing": tracing,
            "error": "LANGSMITH_API_KEY not set",
        }

    try:
        if client_factory is None:
            from langsmith import Client

            client_factory = Client
        client = client_factory(api_key=api_key)
        projects = list(client.list_projects(limit=5))
        return {
            "ok": True,
            "state": "connected",
            "project": project,
            "tracing": tracing,
            "workspace_projects": len(projects),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "state": "auth_failed",
            "project": project,
            "tracing": tracing,
            "error": str(exc)[:200],
        }


def langsmith_stats_payload(status: dict[str, Any] | None) -> dict[str, Any]:
    if not status:
        return {
            "ok": False,
            "state": "unknown",
            "project": "theseus-mission-readiness",
            "tracing": False,
            "workspace_projects": 0,
            "error": "not checked",
        }
    return {
        "ok": bool(status.get("ok")),
        "state": status.get("state") or "unknown",
        "project": status.get("project") or "theseus-mission-readiness",
        "tracing": bool(status.get("tracing")),
        "workspace_projects": int(status.get("workspace_projects") or 0),
        "error": status.get("error"),
    }


def _repo_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def studio_subprocess_env(source: dict[str, str] | None = None) -> dict[str, str]:
    """Full env dict for langgraph dev — inherits process env + .env LangSmith keys."""
    env = dict(source if source is not None else os.environ)
    env_path = _repo_env_path()
    if env_path.is_file():
        for key, value in dotenv_values(env_path).items():
            if value is None:
                continue
            if key in LANGSMITH_ENV_KEYS:
                env[key] = value
    apply_langsmith_env(env, source=env)
    return env


def log_langsmith_startup(status: dict[str, Any] | None, *, logger_obj: Any | None = None) -> None:
    log = logger_obj or logger
    if not status:
        log.info("LangSmith status unavailable")
        return
    if status.get("ok"):
        log.info(
            "LangSmith connected: project=%s tracing=%s workspace_projects=%s",
            status.get("project"),
            status.get("tracing"),
            status.get("workspace_projects"),
        )
        return
    log.warning(
        "LangSmith unavailable: state=%s error=%s",
        status.get("state"),
        status.get("error") or "unknown",
    )