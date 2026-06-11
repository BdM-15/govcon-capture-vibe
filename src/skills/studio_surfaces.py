"""Studio deliverable discovery and huashu deck validation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.skills.run_metadata import (
    humanize_artifact_name,
    is_studio_deliverable,
    read_artifact_manifest,
    sanitize_artifact_display_name,
    write_artifact_manifest,
)

_TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)
_DECK_MANIFEST_RE = re.compile(
    r"window\.DECK_MANIFEST\s*=\s*(\[[\s\S]*?\]);",
    re.MULTILINE,
)


def _safe_relative_artifact_path(rel: str) -> str | None:
    cleaned = str(rel or "").replace("\\", "/").strip().strip("/")
    if not cleaned or ".." in cleaned.split("/"):
        return None
    return cleaned


def _is_slide_asset(rel: str) -> bool:
    parts = rel.lower().split("/")
    return "slides" in parts


def _deck_manifest_entries(index_html: str) -> list[dict[str, Any]]:
    match = _DECK_MANIFEST_RE.search(index_html)
    if not match:
        return []
    try:
        loaded = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def _title_from_html(text: str, *, fallback: str) -> str:
    match = _TITLE_RE.search(text)
    if match:
        title = sanitize_artifact_display_name(match.group(1))
        if title:
            return title
    return fallback


def deck_display_name(index_path: Path) -> str:
    """Human-facing label for a deck index.html artifact."""
    try:
        text = index_path.read_text(encoding="utf-8", errors="replace")[:50_000]
    except OSError:
        text = ""
    folder_label = humanize_artifact_name(index_path.parent.name)
    return _title_from_html(text, fallback=f"{folder_label} HTML Deck")


def validate_deck_index(index_path: Path) -> dict[str, Any]:
    """Check DECK_MANIFEST slide files exist beside the deck index."""
    try:
        text = index_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "complete": False,
            "expected": 0,
            "found": 0,
            "missing": [],
            "error": str(exc),
        }

    entries = _deck_manifest_entries(text)
    if not entries:
        return {
            "complete": True,
            "expected": 0,
            "found": 0,
            "missing": [],
        }

    deck_dir = index_path.parent
    missing: list[str] = []
    found = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("file") or "").strip()
        if not rel:
            continue
        slide_path = (deck_dir / rel).resolve()
        try:
            slide_path.relative_to(deck_dir.resolve())
        except ValueError:
            missing.append(rel)
            continue
        if slide_path.is_file():
            found += 1
        else:
            missing.append(rel)

    expected = len(
        [
            entry
            for entry in entries
            if isinstance(entry, dict) and str(entry.get("file") or "").strip()
        ]
    )
    return {
        "complete": expected > 0 and found == expected,
        "expected": expected,
        "found": found,
        "missing": missing,
    }


def iter_studio_deliverable_paths(artifacts_dir: Path) -> list[tuple[str, Path]]:
    """Return Studio-visible artifact paths under artifacts/ (posix rel, path)."""
    if not artifacts_dir.is_dir():
        return []

    rows: list[tuple[str, Path]] = []
    seen: set[str] = set()

    for path in sorted(artifacts_dir.iterdir()):
        if not path.is_file():
            continue
        if not is_studio_deliverable(path.name):
            continue
        rel = path.name
        rows.append((rel, path))
        seen.add(rel.lower())

    for index_path in sorted(artifacts_dir.rglob("index.html")):
        if not index_path.is_file():
            continue
        rel = index_path.relative_to(artifacts_dir).as_posix()
        if _is_slide_asset(rel) or rel.lower() in seen:
            continue
        try:
            text = index_path.read_text(encoding="utf-8", errors="replace")[:100_000]
        except OSError:
            continue
        if "DECK_MANIFEST" not in text and index_path.parent == artifacts_dir:
            continue
        rows.append((rel, index_path))
        seen.add(rel.lower())

    return rows


def finalize_huashu_studio_surfaces(run_dir: Path) -> list[str]:
    """Label nested deck surfaces and return warnings for incomplete decks."""
    artifacts_dir = Path(run_dir) / "artifacts"
    warnings: list[str] = []
    manifest = read_artifact_manifest(run_dir)

    for rel, index_path in iter_studio_deliverable_paths(artifacts_dir):
        if not rel.endswith("index.html"):
            continue
        try:
            text = index_path.read_text(encoding="utf-8", errors="replace")[:100_000]
        except OSError:
            continue

        display_name = deck_display_name(index_path)
        deck_status = validate_deck_index(index_path)

        entry = dict(manifest.get(rel) or {})
        entry["display_name"] = display_name
        entry["studio_role"] = "final"
        entry["deck_completeness"] = deck_status
        manifest[rel] = entry

        if deck_status.get("expected", 0) and not deck_status.get("complete"):
            missing = deck_status.get("missing") or []
            preview = ", ".join(missing[:4])
            if len(missing) > 4:
                preview += f", +{len(missing) - 4} more"
            warnings.append(
                f"Deck incomplete ({deck_status.get('found', 0)}/"
                f"{deck_status.get('expected', 0)} slides on disk): {preview}"
            )

    for rel, path in iter_studio_deliverable_paths(artifacts_dir):
        if rel.endswith("index.html"):
            continue
        if not is_studio_deliverable(path.name):
            continue
        entry = dict(manifest.get(rel) or {})
        if not entry.get("display_name"):
            entry["display_name"] = humanize_artifact_name(path.name)
        entry.setdefault("studio_role", "final")
        manifest[rel] = entry

    write_artifact_manifest(run_dir, manifest)
    return warnings


__all__ = [
    "deck_display_name",
    "finalize_huashu_studio_surfaces",
    "iter_studio_deliverable_paths",
    "validate_deck_index",
]