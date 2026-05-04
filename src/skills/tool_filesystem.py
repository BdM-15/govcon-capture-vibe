"""Filesystem-backed tool handlers for the skill runtime."""

from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path
from typing import Optional

from src.skills.tool_types import ToolContext, ToolError, ToolResult


def safe_join(base: Path, rel: str) -> Path:
    """Resolve rel under base and reject sandbox escape attempts."""
    if not rel or not isinstance(rel, str):
        raise ToolError("path must be a non-empty string")
    path = Path(rel)
    if path.is_absolute():
        raise ToolError(f"path must be relative, got absolute: {rel!r}")
    candidate = (base / path).resolve()
    base_resolved = base.resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise ToolError(f"path {rel!r} escapes sandbox {base_resolved}") from exc
    return candidate


async def tool_read_file(ctx: ToolContext, path: str) -> ToolResult:
    target = safe_join(ctx.skill_dir, path)
    if not target.exists():
        raise ToolError(f"file not found: {path}")
    if not target.is_file():
        raise ToolError(f"not a regular file: {path}")
    rel = target.relative_to(ctx.skill_dir.resolve()).as_posix()
    if rel != "SKILL.md" and not rel.startswith(("references/", "assets/", "scripts/")):
        raise ToolError(
            f"read_file is restricted to SKILL.md / references/ / assets/ / scripts/ — got {rel!r}"
        )
    size = target.stat().st_size
    truncated = False
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = target.read_text(encoding="latin-1", errors="replace")
    if len(text) > ctx.max_read_bytes:
        text = text[: ctx.max_read_bytes]
        truncated = True
    return ToolResult(
        payload={
            "path": rel,
            "size_bytes": size,
            "truncated": truncated,
            "content": text,
        },
        truncated=truncated,
    )


async def tool_run_script(
    ctx: ToolContext,
    path: str,
    args: Optional[list[str]] = None,
    stdin: Optional[str] = None,
    timeout: Optional[int] = None,
) -> ToolResult:
    skill_root = ctx.skill_dir.resolve()
    target_str = str(path).strip()
    if not target_str:
        raise ToolError("path must be a non-empty string")
    if Path(target_str).is_absolute():
        raise ToolError(f"path must be relative, got absolute: {path!r}")

    candidate = (ctx.skill_dir / target_str).resolve()
    allowed_roots: list[Path] = [(skill_root / "scripts").resolve()]
    allowed_roots.extend(root.resolve() for root in ctx.extra_script_roots)

    matched_root = None
    for root in allowed_roots:
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        matched_root = root
        break
    if matched_root is None:
        roots_display = ", ".join(str(root) for root in allowed_roots) or "(none)"
        raise ToolError(
            f"run_script path {path!r} is outside any allowed root. Allowed roots: {roots_display}. Declare cross-skill script directories via `metadata.script_paths` in your SKILL.md."
        )

    if not candidate.is_file():
        raise ToolError(f"script not found: {path}")
    target = candidate
    try:
        rel = target.relative_to(skill_root).as_posix()
    except ValueError:
        rel = str(target)

    suffix = target.suffix.lower()
    if suffix == ".py":
        import sys as _sys

        cmd = [_sys.executable, str(target)]
    elif suffix == ".sh":
        cmd = ["bash", str(target)]
    elif suffix in (".mjs", ".js"):
        cmd = ["node", str(target)]
    else:
        raise ToolError("unsupported script type {suffix!r}; allowed: .py, .sh, .mjs, .js")

    if args:
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise ToolError("args must be a list of strings")
        if len(args) > 32:
            raise ToolError("args list capped at 32 entries")
        run_dir_abs = str(ctx.run_dir.resolve())
        artifacts_abs = str((ctx.run_dir / "artifacts").resolve())
        skill_dir_abs = str(skill_root)
        substituted: list[str] = []
        for arg in args:
            substituted.append(
                arg.replace("{run_dir}", run_dir_abs)
                .replace("{artifacts}", artifacts_abs)
                .replace("{skill_dir}", skill_dir_abs)
            )
        cmd.extend(substituted)

    effective_timeout = min(
        ctx.max_script_seconds,
        max(1, int(timeout)) if timeout is not None else ctx.max_script_seconds,
    )

    if matched_root == (skill_root / "scripts").resolve():
        cwd = str(ctx.skill_dir)
    else:
        cwd = str(matched_root.parent)

    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            input=stdin or "",
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            cwd=cwd,
            check=False,
        )

    try:
        proc = await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"script timed out after {effective_timeout}s: {rel}") from exc
    except FileNotFoundError as exc:
        raise ToolError(f"script interpreter not found: {exc}") from exc

    seq = ctx.call_seq[0]
    out_dir = ctx.run_dir / "tool_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^A-Za-z0-9._-]+", "_", rel)
    stdout_path = out_dir / f"{seq:03d}_run_script_{safe_label}.stdout.txt"
    stderr_path = out_dir / f"{seq:03d}_run_script_{safe_label}.stderr.txt"
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")

    cap = 4000
    return ToolResult(
        payload={
            "script": rel,
            "exit_code": proc.returncode,
            "timeout_seconds": effective_timeout,
            "stdout": (proc.stdout or "")[:cap],
            "stderr": (proc.stderr or "")[:cap],
            "stdout_truncated": len(proc.stdout or "") > cap,
            "stderr_truncated": len(proc.stderr or "") > cap,
        },
        transcript_extra={
            "stdout_file": str(stdout_path),
            "stderr_file": str(stderr_path),
        },
    )


async def tool_write_file(ctx: ToolContext, path: str, content: str) -> ToolResult:
    if not isinstance(content, str):
        raise ToolError("content must be a string")
    if len(content.encode("utf-8")) > ctx.max_write_bytes:
        raise ToolError(
            f"content exceeds max_write_bytes ({ctx.max_write_bytes}); split into smaller artifacts"
        )
    artifacts_root = ctx.run_dir / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    cleaned = path.lstrip("/\\")
    if cleaned.lower().startswith("artifacts/") or cleaned.lower().startswith("artifacts\\"):
        cleaned = cleaned[len("artifacts/"):]
    target = safe_join(artifacts_root, cleaned)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    rel = target.relative_to(ctx.run_dir.resolve()).as_posix()
    return ToolResult(payload={"path": rel, "bytes_written": len(content.encode("utf-8"))})