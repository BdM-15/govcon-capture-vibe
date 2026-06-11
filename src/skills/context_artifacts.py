"""Resolve Studio deliverables for direct skill-invoke artifact handoff."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.skills.run_metadata import resolve_artifact_display_name, resolve_artifact_mime

MAX_CONTEXT_ARTIFACTS = 5
MAX_EXCERPT_CHARS = 12_000

_TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".csv",
    ".tsv",
    ".html",
    ".htm",
    ".xml",
    ".yaml",
    ".yml",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".css",
}
_BINARY_NOTE_EXTENSIONS = {
    ".docx",
    ".xlsx",
    ".xlsm",
    ".pptx",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".zip",
}


class ContextArtifactRef(BaseModel):
    """Studio artifact reference for skill invoke (skill + run + filename)."""

    model_config = ConfigDict(extra="forbid")

    skill: str = Field(..., min_length=1, max_length=128)
    run_id: str = Field(..., min_length=1, max_length=128)
    filename: str = Field(..., min_length=1, max_length=255)


class ResolvedContextArtifact(BaseModel):
    """Resolved artifact with absolute path and optional text excerpt."""

    model_config = ConfigDict(extra="forbid")

    skill: str
    run_id: str
    filename: str
    path: str
    display_name: str = ""
    mime: str = ""
    size: int = 0
    excerpt: str = ""
    excerpt_truncated: bool = False
    note: str = ""


def _read_text_excerpt(path: Path, *, max_chars: int) -> tuple[str, bool, str]:
    suffix = path.suffix.lower()
    if suffix in _BINARY_NOTE_EXTENSIONS:
        return (
            "",
            False,
            f"Binary deliverable ({suffix or 'unknown'}); use read_workspace_artifact for full content.",
        )
    if suffix and suffix not in _TEXT_EXTENSIONS:
        return (
            "",
            False,
            f"Non-text deliverable ({suffix}); use read_workspace_artifact if needed.",
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            raw = path.read_text(encoding="latin-1", errors="replace")
        except OSError as exc:
            return "", False, f"Could not read file: {exc}"
    except OSError as exc:
        return "", False, f"Could not read file: {exc}"

    if suffix == ".json":
        try:
            parsed = json.loads(raw)
            raw = json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass

    truncated = len(raw) > max_chars
    excerpt = raw[:max_chars] if truncated else raw
    return excerpt, truncated, ""


def resolve_context_artifacts(
    workspace_root: Path,
    refs: list[ContextArtifactRef],
    *,
    get_artifact_path: Callable[[Path, str, str, str], Optional[Path]],
    max_artifacts: int = MAX_CONTEXT_ARTIFACTS,
    max_excerpt_chars: int = MAX_EXCERPT_CHARS,
) -> tuple[list[ResolvedContextArtifact], list[str]]:
    """Resolve refs to safe paths and inline excerpts for prompt injection."""
    if not refs:
        return [], []
    if len(refs) > max_artifacts:
        return [], [f"At most {max_artifacts} context artifacts allowed"]

    resolved: list[ResolvedContextArtifact] = []
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    for ref in refs[:max_artifacts]:
        key = (ref.skill, ref.run_id, ref.filename)
        if key in seen:
            continue
        seen.add(key)

        path = get_artifact_path(workspace_root, ref.skill, ref.run_id, ref.filename)
        if path is None:
            errors.append(
                f"Artifact not found: {ref.skill}/{ref.run_id}/{ref.filename}"
            )
            continue

        try:
            size = path.stat().st_size
        except OSError:
            size = 0

        excerpt, excerpt_truncated, note = _read_text_excerpt(
            path,
            max_chars=max_excerpt_chars,
        )
        resolved.append(
            ResolvedContextArtifact(
                skill=ref.skill,
                run_id=ref.run_id,
                filename=ref.filename,
                path=str(path.resolve()),
                display_name=resolve_artifact_display_name(ref.filename),
                mime=resolve_artifact_mime(ref.filename),
                size=size,
                excerpt=excerpt,
                excerpt_truncated=excerpt_truncated,
                note=note,
            )
        )

    return resolved, errors


def to_input_artifacts_payload(
    resolved: list[ResolvedContextArtifact],
) -> list[dict[str, Any]]:
    """Chain-compatible input_artifacts list for tools and entity_payload."""
    return [
        {
            "step_id": "context",
            "skill": artifact.skill,
            "run_id": artifact.run_id,
            "filename": artifact.filename,
            "path": artifact.path,
            "display_name": artifact.display_name or artifact.filename,
            "mime": artifact.mime,
            "size": artifact.size,
            "products": [],
        }
        for artifact in resolved
    ]


def format_context_artifacts_prompt_block(
    resolved: list[ResolvedContextArtifact],
) -> str:
    """Human-readable prompt section appended before skill execution."""
    if not resolved:
        return ""

    lines = [
        "## Attached Studio Artifacts",
        (
            "Prior-run deliverables attached as context. Use input_artifacts[].path "
            "with read_workspace_artifact for full content; do not reconstruct paths."
        ),
    ]
    for index, artifact in enumerate(resolved, start=1):
        label = artifact.display_name or artifact.filename
        lines.append(
            f"\n### Artifact {index}: {label} "
            f"({artifact.skill}/{artifact.run_id}/{artifact.filename})"
        )
        lines.append(f"- path: `{artifact.path}`")
        if artifact.mime:
            lines.append(f"- mime: {artifact.mime}")
        if artifact.size:
            lines.append(f"- size: {artifact.size} bytes")
        if artifact.note:
            lines.append(f"- note: {artifact.note}")
        if artifact.excerpt:
            lines.append("```")
            lines.append(artifact.excerpt)
            if artifact.excerpt_truncated:
                lines.append(
                    f"…[excerpt truncated at {MAX_EXCERPT_CHARS} chars; "
                    "use read_workspace_artifact for remainder]"
                )
            lines.append("```")

    handoff = {
        "input_artifacts": to_input_artifacts_payload(resolved),
        "context_artifacts": [artifact.model_dump() for artifact in resolved],
    }
    lines.append("\n## Theseus Artifact Handoff")
    lines.append("```json")
    lines.append(json.dumps(handoff, ensure_ascii=False, indent=2, default=str))
    lines.append("```")
    return "\n".join(lines)


__all__ = [
    "ContextArtifactRef",
    "MAX_CONTEXT_ARTIFACTS",
    "MAX_EXCERPT_CHARS",
    "ResolvedContextArtifact",
    "format_context_artifacts_prompt_block",
    "resolve_context_artifacts",
    "to_input_artifacts_payload",
]