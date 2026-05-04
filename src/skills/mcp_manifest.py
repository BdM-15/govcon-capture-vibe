"""Manifest loading and discovery for vendored MCP servers."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MCPManifest:
    """Theseus-side description of a vendored MCP server."""

    name: str
    description: str
    command: list[str]
    cwd: Path
    env_required: list[str] = field(default_factory=list)
    env_optional: list[str] = field(default_factory=list)
    vendored_from: str = ""
    vendored_commit: str = ""
    vendored_at: str = ""
    license: str = ""

    def missing_env(self, env: Optional[dict[str, str]] = None) -> list[str]:
        """Return required env vars absent from env or os.environ."""
        scope = env if env is not None else os.environ
        return [key for key in self.env_required if not scope.get(key)]


def load_manifest(manifest_path: Path) -> MCPManifest:
    """Parse tools/mcps/<name>/theseus_manifest.json."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"manifest {manifest_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"manifest {manifest_path}: top-level must be a JSON object")
    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError(f"manifest {manifest_path}: missing 'name'")
    command = raw.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(entry, str) for entry in command):
        raise ValueError(
            f"manifest {manifest_path}: 'command' must be a non-empty list of strings"
        )
    return MCPManifest(
        name=name,
        description=str(raw.get("description") or ""),
        command=list(command),
        cwd=manifest_path.parent.resolve(),
        env_required=[str(entry) for entry in (raw.get("env_required") or [])],
        env_optional=[str(entry) for entry in (raw.get("env_optional") or [])],
        vendored_from=str(raw.get("vendored_from") or ""),
        vendored_commit=str(raw.get("vendored_commit") or ""),
        vendored_at=str(raw.get("vendored_at") or ""),
        license=str(raw.get("license") or ""),
    )


def discover_manifests(mcps_root: Path) -> dict[str, MCPManifest]:
    """Scan tools/mcps/*/theseus_manifest.json into a name -> manifest map."""
    found: dict[str, MCPManifest] = {}
    if not mcps_root.is_dir():
        logger.debug("MCP root %s does not exist; no manifests loaded", mcps_root)
        return found
    for child in sorted(mcps_root.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "theseus_manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = load_manifest(manifest_path)
        except (ValueError, FileNotFoundError) as exc:
            logger.warning("Skipping MCP at %s: %s", child, exc)
            continue
        if manifest.name in found:
            logger.warning(
                "Duplicate MCP name %r (second copy at %s) — keeping first",
                manifest.name,
                child,
            )
            continue
        found[manifest.name] = manifest
    return found