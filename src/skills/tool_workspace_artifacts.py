"""Read prior skill-run artifacts attached to an invoke."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.skills.run_metadata import resolve_artifact_mime
from src.skills.tool_types import ToolContext, ToolError, ToolResult


def _artifact_key(skill: str, run_id: str, filename: str) -> tuple[str, str, str]:
    return (
        str(skill or "").strip(),
        str(run_id or "").strip(),
        str(filename or "").strip(),
    )


def _attached_index(ctx: ToolContext) -> dict[tuple[str, str, str], dict[str, Any]]:
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in ctx.attached_artifacts or []:
        if not isinstance(entry, dict):
            continue
        key = _artifact_key(
            str(entry.get("skill") or ""),
            str(entry.get("run_id") or ""),
            str(entry.get("filename") or ""),
        )
        if key[2]:
            index[key] = entry
    return index


async def tool_read_workspace_artifact(
    ctx: ToolContext,
    skill: str,
    run_id: str,
    filename: str,
) -> ToolResult:
    """Read a Studio deliverable that was attached to this invoke."""
    key = _artifact_key(skill, run_id, filename)
    if not key[2]:
        raise ToolError("filename is required")

    attached = _attached_index(ctx).get(key)
    if attached is None:
        raise ToolError(
            f"artifact not attached to this invoke: {skill}/{run_id}/{filename}"
        )

    path_value = str(attached.get("path") or "").strip()
    if not path_value:
        raise ToolError(f"attached artifact has no path: {skill}/{run_id}/{filename}")

    target = Path(path_value).resolve()
    if not target.is_file():
        raise ToolError(f"artifact file missing on disk: {target}")

    workspace_root = ctx.workspace_dir.resolve()
    runs_root = (workspace_root / "skill_runs").resolve()
    try:
        target.relative_to(runs_root)
    except ValueError as exc:
        raise ToolError("artifact path is outside workspace skill_runs") from exc

    try:
        size = target.stat().st_size
    except OSError as exc:
        raise ToolError(f"unable to stat artifact: {exc}") from exc

    suffix = target.suffix.lower()
    mime = str(attached.get("mime") or resolve_artifact_mime(target.name))
    truncated = False
    note = ""

    if suffix == ".json":
        try:
            parsed = json.loads(target.read_text(encoding="utf-8"))
            content = json.dumps(parsed, ensure_ascii=False, indent=2)
        except (OSError, json.JSONDecodeError) as exc:
            raise ToolError(f"unable to read JSON artifact: {exc}") from exc
    elif suffix in {".docx", ".xlsx", ".xlsm", ".pptx", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip"}:
        content = ""
        note = (
            f"Binary deliverable ({suffix}); download from Studio or use run_script "
            "renderers when conversion is required."
        )
    else:
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = target.read_text(encoding="latin-1", errors="replace")
        except OSError as exc:
            raise ToolError(f"unable to read artifact: {exc}") from exc

    if content and len(content) > ctx.max_read_bytes:
        content = content[: ctx.max_read_bytes]
        truncated = True

    return ToolResult(
        payload={
            "skill": key[0],
            "run_id": key[1],
            "filename": key[2],
            "path": str(target),
            "mime": mime,
            "size_bytes": size,
            "truncated": truncated,
            "note": note,
            "content": content,
        },
        truncated=truncated,
    )