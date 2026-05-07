"""Pure helpers for skill run metadata, mime resolution, and listing."""

from __future__ import annotations

import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ARTIFACT_MANIFEST_FILENAME = "artifacts_manifest.json"

# Mimetypes the stdlib ``mimetypes`` module misses on Windows / fresh installs.
# Used by the Studio UI to label skill artifact rows and download responses.
STUDIO_EXTRA_MIME: dict[str, str] = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "html": "text/html",
    "htm": "text/html",
    "md": "text/markdown",
    "json": "application/json",
    "gif": "image/gif",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "pdf": "application/pdf",
}

STUDIO_DELIVERABLE_EXTENSIONS = {
    "docx",
    "xlsx",
    "pptx",
    "pdf",
    "html",
    "htm",
    "mp4",
    "gif",
    "png",
    "jpg",
    "jpeg",
    "webp",
}


def is_studio_deliverable(filename: str) -> bool:
    """Return true for polished final products shown in Studio."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in STUDIO_DELIVERABLE_EXTENSIONS


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


def sanitize_artifact_display_name(value: Any, max_len: int = 120) -> str | None:
    """Normalize a user-facing artifact label or return None."""
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return None
    return cleaned[:max_len].rstrip()


def humanize_artifact_name(filename: str) -> str:
    """Turn a raw artifact filename into a readable fallback title."""
    leaf = Path(filename or "artifact").name
    stem = Path(leaf).stem or leaf
    tokens = [token for token in re.split(r"[_\-]+", stem) if token]
    if not tokens:
        return leaf

    def _pretty(token: str) -> str:
        if any(char.isdigit() for char in token) or token.upper() == token:
            return token
        return token.capitalize()

    return " ".join(_pretty(token) for token in tokens)


def artifact_manifest_path(run_dir: Path) -> Path:
    """Return the manifest path that stores per-artifact UI metadata."""
    return run_dir / ARTIFACT_MANIFEST_FILENAME


def read_artifact_manifest(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Load per-artifact metadata for one run, or an empty dict."""
    path = artifact_manifest_path(run_dir)
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unreadable artifact manifest at %s: %s", path, exc)
        return {}
    if not isinstance(loaded, dict):
        return {}

    out: dict[str, dict[str, Any]] = {}
    for key, value in loaded.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        normalized: dict[str, Any] = {}
        display_name = sanitize_artifact_display_name(value.get("display_name"))
        if display_name:
            normalized["display_name"] = display_name
        render_status = str(value.get("render_status") or "").strip().lower()
        if render_status == "failed":
            normalized["render_status"] = render_status
        render_message = str(value.get("render_message") or "").strip()
        if render_message:
            normalized["render_message"] = render_message[:400]
        render_targets = value.get("render_targets")
        if isinstance(render_targets, list):
            cleaned_targets = []
            for item in render_targets:
                text = str(item or "").strip()
                if text and text not in cleaned_targets:
                    cleaned_targets.append(text[:160])
                if len(cleaned_targets) >= 8:
                    break
            if cleaned_targets:
                normalized["render_targets"] = cleaned_targets
        render_logs = value.get("render_logs")
        if isinstance(render_logs, list):
            cleaned_logs = []
            for item in render_logs:
                text = str(item or "").strip()
                if text and text not in cleaned_logs:
                    cleaned_logs.append(text[:160])
                if len(cleaned_logs) >= 8:
                    break
            if cleaned_logs:
                normalized["render_logs"] = cleaned_logs
        render_log_excerpt = str(value.get("render_log_excerpt") or "").strip()
        if render_log_excerpt:
            normalized["render_log_excerpt"] = render_log_excerpt[:1200]
        if normalized:
            out[key] = normalized
    return out


def write_artifact_manifest(run_dir: Path, manifest: dict[str, dict[str, Any]]) -> None:
    """Persist per-artifact metadata for one run."""
    artifact_manifest_path(run_dir).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def resolve_artifact_display_name(
    filename: str,
    manifest_entry: dict[str, Any] | None = None,
) -> str:
    """Return explicit label when present, else a readable fallback."""
    if manifest_entry:
        explicit = sanitize_artifact_display_name(manifest_entry.get("display_name"))
        if explicit:
            return explicit
    return humanize_artifact_name(filename)


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


def list_run_artifacts(run_dir: Path) -> list[dict[str, Any]]:
    """List artifacts under one skill run's artifacts/ directory."""
    artifacts: list[dict[str, Any]] = []
    artifacts_dir = run_dir / "artifacts"
    manifest = read_artifact_manifest(run_dir)
    if artifacts_dir.is_dir():
        for path in sorted(artifacts_dir.iterdir()):
            if path.is_file():
                rel = path.relative_to(artifacts_dir).as_posix()
                manifest_entry = manifest.get(rel)
                artifacts.append(
                    {
                        "name": path.name,
                        "size": str(path.stat().st_size),
                        "mime": resolve_artifact_mime(path.name),
                        "display_name": resolve_artifact_display_name(
                            path.name,
                            manifest_entry,
                        ),
                        **{
                            key: value
                            for key, value in (manifest_entry or {}).items()
                            if key != "display_name"
                        },
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