"""Engine stack versions — expected targets from .env, installed from package metadata."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib import metadata
from typing import Any

from packaging.version import InvalidVersion, Version

logger = logging.getLogger(__name__)

MINERU_DISTRIBUTION = "mineru"
LIGHTRAG_DISTRIBUTION = "lightrag-hku"

_STACK_DISTRIBUTIONS: tuple[tuple[str, str], ...] = (
    ("lightrag", LIGHTRAG_DISTRIBUTION),
    ("mineru", MINERU_DISTRIBUTION),
    ("transformers", "transformers"),
    ("langgraph", "langgraph"),
)


@dataclass(frozen=True)
class MineruStackVersion:
    """Declared MinerU target (.env) vs installed package version."""

    expected: str
    installed: str
    aligned: bool


def resolve_installed_version(distribution: str, *, import_name: str | None = None) -> str:
    """Return an installed distribution version or ``unknown``."""
    candidates = (distribution,)
    if import_name and import_name != distribution:
        candidates = (distribution, import_name)
    for candidate in candidates:
        try:
            return metadata.version(candidate)
        except metadata.PackageNotFoundError:
            continue
    return "unknown"


def normalize_expected_version(expected: str) -> str:
    """Normalize ``3.3`` style pins to a PEP 440 version for comparison."""
    value = str(expected or "").strip()
    if not value:
        return "0"
    if value.count(".") == 1:
        return f"{value}.0"
    return value


def mineru_versions_aligned(installed: str, expected: str) -> bool:
    """True when the installed MinerU package satisfies the .env target."""
    if installed == "unknown":
        return False
    target = normalize_expected_version(expected)
    try:
        return Version(installed) >= Version(target)
    except InvalidVersion:
        return installed.startswith(str(expected).strip())


def resolve_mineru_stack_version(expected: str) -> MineruStackVersion:
    expected_value = str(expected or "3.3").strip() or "3.3"
    installed = resolve_installed_version(MINERU_DISTRIBUTION)
    return MineruStackVersion(
        expected=expected_value,
        installed=installed,
        aligned=mineru_versions_aligned(installed, expected_value),
    )


def build_engine_stack_payload(*, mineru_expected: str) -> dict[str, Any]:
    """Build dashboard/API stack version payload."""
    mineru = resolve_mineru_stack_version(mineru_expected)
    payload: dict[str, Any] = {
        "mineru_expected": mineru.expected,
        "mineru_aligned": mineru.aligned,
    }
    for key, distribution in _STACK_DISTRIBUTIONS:
        payload[key] = resolve_installed_version(distribution, import_name=key)
    payload["mineru"] = mineru.installed
    return payload


def log_mineru_stack_version(*, expected: str, prefix: str = "MinerU stack") -> MineruStackVersion:
    """Log expected vs installed MinerU versions; warn when misaligned."""
    stack = resolve_mineru_stack_version(expected)
    if stack.aligned:
        logger.info(
            "%s: target=%s installed=v%s (aligned)",
            prefix,
            stack.expected,
            stack.installed,
        )
    else:
        logger.warning(
            "%s: target=%s installed=v%s — run `uv sync` to align with pyproject.toml",
            prefix,
            stack.expected,
            stack.installed,
        )
    return stack


def format_mineru_banner_version(stack: MineruStackVersion, colors: Any) -> str:
    """Render MinerU version row fragment for the startup banner."""
    if stack.installed == "unknown":
        return (
            f"{colors.YELLOW}not installed{colors.RESET}  ·  "
            f"target {colors.CYAN}{stack.expected}{colors.RESET}"
        )
    if stack.aligned:
        return (
            f"{colors.DIM}v{stack.installed}{colors.RESET}  ·  "
            f"target {colors.DIM}{stack.expected}{colors.RESET}"
        )
    return (
        f"{colors.YELLOW}v{stack.installed}{colors.RESET}  ·  "
        f"target {colors.CYAN}{stack.expected}{colors.RESET}  "
        f"{colors.YELLOW}⚠ mismatch — uv sync{colors.RESET}"
    )


__all__ = [
    "MineruStackVersion",
    "build_engine_stack_payload",
    "format_mineru_banner_version",
    "log_mineru_stack_version",
    "mineru_versions_aligned",
    "normalize_expected_version",
    "resolve_installed_version",
    "resolve_mineru_stack_version",
]