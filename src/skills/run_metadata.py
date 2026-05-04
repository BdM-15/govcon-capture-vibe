"""Pure helpers for skill run metadata, mime resolution, and listing."""

from __future__ import annotations

import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Mimetypes the stdlib ``mimetypes`` module misses on Windows / fresh installs.
# Used by the Studio UI to label skill artifact rows and download responses.
STUDIO_EXTRA_MIME: dict[str, str] = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "md": "text/markdown",
    "json": "application/json",
    "gif": "image/gif",
    "mp4": "video/mp4",
    "pdf": "application/pdf",
}


def resolve_artifact_mime(filename: str) -> str:
    """Resolve a stable mime type for a skill artifact filename."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in STUDIO_EXTRA_MIME:
        return STUDIO_EXTRA_MIME[ext]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def slugify_for_filename(text: str, max_len: int = 32) -> str:
    """Lowercase + non-alphanumeric to underscore + length cap."""
    if not text:
        return ""
    cleaned = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return cleaned[:max_len].rstrip("_")


def parse_run_envelope(text: str) -> dict[str, Any]:
    """Extract the YAML-ish frontmatter from a run.md envelope."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, Any] = {}
    for raw in lines[1:]:
        if raw.strip() == "---":
            break
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$", raw)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if key in {"elapsed_ms", "response_chars"}:
            try:
                out[key] = int(value)
                continue
            except ValueError:
                pass
        if key == "entities_used" and value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            out[key] = [item.strip() for item in inner.split(",") if item.strip()] if inner else []
            continue
        out[key] = value

    try:
        body_start = text.find("\n## User Prompt\n")
        if body_start >= 0:
            tail = text[body_start + len("\n## User Prompt\n") :].strip()
            preview = tail.split("\n## ", 1)[0].strip()
            out["prompt_preview"] = preview[:160] + "..." if len(preview) > 160 else preview
    except Exception:  # noqa: BLE001
        pass
    return out


def list_run_artifacts(run_dir: Path) -> list[dict[str, str]]:
    """List artifacts under one skill run's artifacts/ directory."""
    artifacts: list[dict[str, str]] = []
    artifacts_dir = run_dir / "artifacts"
    if artifacts_dir.is_dir():
        for path in sorted(artifacts_dir.iterdir()):
            if path.is_file():
                artifacts.append(
                    {
                        "name": path.name,
                        "size": str(path.stat().st_size),
                        "mime": resolve_artifact_mime(path.name),
                    }
                )
    return artifacts


def read_run_transcript(run_dir: Path) -> list[dict[str, Any]]:
    """Read one run's persisted transcript if present and valid."""
    transcript_path = run_dir / "transcript.json"
    if not transcript_path.exists():
        return []
    try:
        loaded = json.loads(transcript_path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            return loaded
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unreadable transcript at %s: %s", transcript_path, exc)
    return []


def list_tool_outputs(run_dir: Path) -> list[dict[str, str]]:
    """List captured tool output files for one run."""
    tool_outputs: list[dict[str, str]] = []
    tool_outputs_dir = run_dir / "tool_outputs"
    if tool_outputs_dir.is_dir():
        for path in sorted(tool_outputs_dir.iterdir()):
            if path.is_file():
                tool_outputs.append({"name": path.name, "size": str(path.stat().st_size)})
    return tool_outputs


def read_run_metadata(run_dir: Path) -> dict[str, Any]:
    """Read parsed metadata from one run's run.md envelope."""
    envelope_path = run_dir / "run.md"
    if not envelope_path.exists():
        return {}
    try:
        return parse_run_envelope(envelope_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}