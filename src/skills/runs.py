"""Persistence and indexing for skill run artifacts."""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from src.skills.run_metadata import (
    STUDIO_EXTRA_MIME,
    list_run_artifacts,
    list_tool_outputs,
    parse_run_envelope,
    read_artifact_manifest,
    read_run_metadata,
    read_run_transcript,
    resolve_artifact_display_name,
    resolve_artifact_mime,
    is_studio_deliverable,
    slugify_for_filename,
    write_artifact_manifest,
)

_SAFE_RUN_ID = re.compile(r"^[0-9]{8}_[0-9]{6}_[a-z0-9_-]+$")


class SkillRunIndex:
    """Own disk-walking and detail reads under a ``skill_runs/`` root."""

    def __init__(self, base: Path) -> None:
        self._base = base

    def _targets(self, *, skill_name: Optional[str] = None) -> list[Path]:
        if not self._base.is_dir():
            return []
        if skill_name:
            return [self._base / skill_name]
        return [path for path in self._base.iterdir() if path.is_dir()]

    def _iter_run_dirs(self, *, skill_name: Optional[str] = None):
        for skill_root in self._targets(skill_name=skill_name):
            if not skill_root.is_dir():
                continue
            for run_dir in skill_root.iterdir():
                if run_dir.is_dir():
                    yield skill_root.name, run_dir

    def list_runs(
        self,
        *,
        skill_name: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for derived_skill_name, run_dir in self._iter_run_dirs(skill_name=skill_name):
            envelope = run_dir / "run.md"
            response_path = run_dir / "response.md"
            if not envelope.exists():
                continue
            meta = parse_run_envelope(envelope.read_text(encoding="utf-8"))
            meta["run_id"] = meta.get("run_id") or run_dir.name
            meta["skill"] = meta.get("skill") or derived_skill_name
            if response_path.exists():
                try:
                    meta["response_chars"] = response_path.stat().st_size
                except OSError:
                    pass
            runs.append(meta)
        runs.sort(key=lambda run: run.get("created_at", ""), reverse=True)
        return runs[:limit]

    def read_run(
        self,
        skill_name: str,
        run_id: str,
        *,
        is_safe_run_id: Callable[[str], bool],
    ) -> Optional[dict[str, Any]]:
        if not is_safe_run_id(run_id):
            return None
        run_dir = self._base / skill_name / run_id
        if not run_dir.is_dir():
            return None
        envelope_path = run_dir / "run.md"
        response_path = run_dir / "response.md"
        prompt_path = run_dir / "prompt.md"
        meta = (
            parse_run_envelope(envelope_path.read_text(encoding="utf-8"))
            if envelope_path.exists()
            else {}
        )
        return {
            "run_id": run_id,
            "skill": skill_name,
            "run_dir": str(run_dir.resolve()),
            "metadata": meta,
            "response": response_path.read_text(encoding="utf-8")
            if response_path.exists()
            else "",
            "prompt": prompt_path.read_text(encoding="utf-8")
            if prompt_path.exists()
            else "",
            "artifacts": list_run_artifacts(run_dir),
            "transcript": read_run_transcript(run_dir),
            "tool_outputs": list_tool_outputs(run_dir),
        }

    def list_deliverables(
        self,
        *,
        is_safe_run_id: Callable[[str], bool],
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for skill_name, run_dir in self._iter_run_dirs():
            if not is_safe_run_id(run_dir.name):
                continue
            artifacts_dir = run_dir / "artifacts"
            if not artifacts_dir.is_dir():
                continue

            meta = read_run_metadata(run_dir)
            manifest = read_artifact_manifest(run_dir)
            created_at = meta.get("created_at") or ""
            title = meta.get("title")

            for artifact in sorted(artifacts_dir.iterdir()):
                if not artifact.is_file():
                    continue
                if not is_studio_deliverable(artifact.name):
                    continue
                try:
                    stat = artifact.stat()
                except OSError:
                    continue
                rel = artifact.relative_to(artifacts_dir).as_posix()
                rows.append(
                    {
                        "skill": skill_name,
                        "run_id": run_dir.name,
                        "filename": artifact.name,
                        "display_name": resolve_artifact_display_name(
                            artifact.name,
                            manifest.get(rel),
                        ),
                        "mime": resolve_artifact_mime(artifact.name),
                        "size": stat.st_size,
                        "created_at": created_at
                        or datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                        "title": title,
                        "ext": artifact.suffix.lstrip(".").lower(),
                    }
                )

        rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
        return rows[:limit]


def build_legacy_run_envelope(
    *,
    run_id: str,
    skill_name: str,
    workspace: str,
    user_prompt: str,
    response: str,
    entities_used: list[str],
    warnings: list[str],
    elapsed_ms: int,
    started_at: datetime,
) -> str:
    return (
        "---\n"
        f"run_id: {run_id}\n"
        f"skill: {skill_name}\n"
        f"workspace: {workspace}\n"
        f"created_at: {started_at.isoformat()}\n"
        f"elapsed_ms: {elapsed_ms}\n"
        f"entities_used: [{', '.join(entities_used)}]\n"
        f"response_chars: {len(response)}\n"
        "---\n\n"
        "# Skill Run\n\n"
        "## User Prompt\n\n"
        f"{user_prompt.strip() or '(skill defaults)'}\n\n"
        "## Warnings\n\n"
        + ("\n".join(f"- {warning}" for warning in warnings) if warnings else "- (none)")
        + "\n\n## See also\n\n"
        "- `response.md` - raw LLM response\n"
        "- `prompt.md` - full composed prompt sent to the model\n"
        "- `artifacts/` - rendered files (when renderers are wired)\n"
    )


def build_tools_run_envelope(
    *,
    run_id: str,
    skill_name: str,
    workspace: str,
    user_prompt: str,
    response: str,
    turns: int,
    tool_calls: int,
    finish_reason: str,
    usage_total: dict[str, int],
    warnings: list[str],
    elapsed_ms: int,
    started_at: datetime,
) -> str:
    return (
        "---\n"
        f"run_id: {run_id}\n"
        f"skill: {skill_name}\n"
        f"workspace: {workspace}\n"
        "runtime: tools\n"
        f"created_at: {started_at.isoformat()}\n"
        f"elapsed_ms: {elapsed_ms}\n"
        f"turns: {turns}\n"
        f"tool_calls: {tool_calls}\n"
        f"finish_reason: {finish_reason}\n"
        f"prompt_tokens: {usage_total.get('prompt_tokens', 0)}\n"
        f"completion_tokens: {usage_total.get('completion_tokens', 0)}\n"
        f"total_tokens: {usage_total.get('total_tokens', 0)}\n"
        f"response_chars: {len(response)}\n"
        "---\n\n"
        "# Skill Run (tools mode)\n\n"
        "## User Prompt\n\n"
        f"{user_prompt.strip() or '(skill defaults)'}\n\n"
        "## Warnings\n\n"
        + ("\n".join(f"- {warning}" for warning in warnings) if warnings else "- (none)")
        + "\n\n## See also\n\n"
        "- `response.md` - final assistant message\n"
        "- `transcript.json` - full turn-by-turn record (tool calls + results)\n"
        "- `tool_outputs/` - raw stdout/stderr from `run_script` calls\n"
        "- `artifacts/` - files the skill wrote with `write_file`\n"
    )


def list_runs_under_base(
    base: Path,
    *,
    skill_name: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List persisted skill runs, newest first."""
    return SkillRunIndex(base).list_runs(skill_name=skill_name, limit=limit)


def read_run_under_base(
    base: Path,
    *,
    skill_name: str,
    run_id: str,
    is_safe_run_id: Callable[[str], bool],
) -> Optional[dict[str, Any]]:
    """Read one persisted run by skill + run id."""
    return SkillRunIndex(base).read_run(
        skill_name,
        run_id,
        is_safe_run_id=is_safe_run_id,
    )


def list_deliverables_under_base(
    base: Path,
    *,
    is_safe_run_id: Callable[[str], bool],
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Flatten every artifact across every skill run into one feed."""
    return SkillRunIndex(base).list_deliverables(
        is_safe_run_id=is_safe_run_id,
        limit=limit,
    )


class SkillRunStore:
    """Filesystem store for skill run envelopes, outputs, and artifacts."""

    @staticmethod
    def runs_root(workspace_root: Path, skill_name: str) -> Path:
        return Path(workspace_root) / "skill_runs" / skill_name

    @staticmethod
    def is_safe_run_id(run_id: str) -> bool:
        return bool(_SAFE_RUN_ID.match(run_id))

    def create_run_dir(
        self,
        *,
        workspace_root: Path,
        skill_name: str,
        user_prompt: str,
        started_at: datetime,
        create_tool_outputs: bool = False,
    ) -> tuple[str, Path]:
        ts = started_at.strftime("%Y%m%d_%H%M%S")
        slug = slugify_for_filename(user_prompt) or "run"
        run_id = f"{ts}_{slug}"
        run_dir = self.runs_root(workspace_root, skill_name) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "artifacts").mkdir(exist_ok=True)
        if create_tool_outputs:
            (run_dir / "tool_outputs").mkdir(exist_ok=True)
        return run_id, run_dir

    def persist_legacy_run(
        self,
        *,
        workspace_root: Path,
        skill_name: str,
        workspace: str,
        user_prompt: str,
        composed_prompt: str,
        response: str,
        entities_used: list[str],
        warnings: list[str],
        elapsed_ms: int,
        started_at: datetime,
    ) -> tuple[str, str]:
        """Write run.md, response.md, and prompt.md for a legacy invocation."""
        run_id, run_dir = self.create_run_dir(
            workspace_root=workspace_root,
            skill_name=skill_name,
            user_prompt=user_prompt,
            started_at=started_at,
        )
        envelope = build_legacy_run_envelope(
            run_id=run_id,
            skill_name=skill_name,
            workspace=workspace,
            user_prompt=user_prompt,
            response=response,
            entities_used=entities_used,
            warnings=warnings,
            elapsed_ms=elapsed_ms,
            started_at=started_at,
        )
        (run_dir / "run.md").write_text(envelope, encoding="utf-8")
        (run_dir / "response.md").write_text(response, encoding="utf-8")
        (run_dir / "prompt.md").write_text(composed_prompt, encoding="utf-8")
        return run_id, str(run_dir.resolve())

    @staticmethod
    def persist_tools_run(
        *,
        run_dir: Path,
        run_id: str,
        skill_name: str,
        workspace: str,
        user_prompt: str,
        response: str,
        turns: int,
        tool_calls: int,
        finish_reason: str,
        usage_total: dict[str, int],
        warnings: list[str],
        elapsed_ms: int,
        started_at: datetime,
    ) -> None:
        """Write run.md and response.md for a tools-mode invocation."""
        envelope = build_tools_run_envelope(
            run_id=run_id,
            skill_name=skill_name,
            workspace=workspace,
            user_prompt=user_prompt,
            response=response,
            turns=turns,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage_total=usage_total,
            warnings=warnings,
            elapsed_ms=elapsed_ms,
            started_at=started_at,
        )
        (run_dir / "run.md").write_text(envelope, encoding="utf-8")
        (run_dir / "response.md").write_text(response or "", encoding="utf-8")

    def list_runs(
        self, workspace_root: Path, skill_name: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        return SkillRunIndex(Path(workspace_root) / "skill_runs").list_runs(
            skill_name=skill_name,
            limit=limit,
        )

    def get_run(
        self, workspace_root: Path, skill_name: str, run_id: str
    ) -> Optional[dict[str, Any]]:
        """Return the full content of a single persisted run, or None."""
        return read_run_under_base(
            Path(workspace_root) / "skill_runs",
            skill_name=skill_name,
            run_id=run_id,
            is_safe_run_id=self.is_safe_run_id,
        )

    def delete_run(self, workspace_root: Path, skill_name: str, run_id: str) -> bool:
        if not self.is_safe_run_id(run_id):
            return False
        run_dir = self.runs_root(workspace_root, skill_name) / run_id
        if not run_dir.is_dir():
            return False
        shutil.rmtree(run_dir, ignore_errors=True)
        return not run_dir.exists()

    def list_deliverables(
        self, workspace_root: Path, limit: int = 500
    ) -> list[dict[str, Any]]:
        return SkillRunIndex(Path(workspace_root) / "skill_runs").list_deliverables(
            is_safe_run_id=self.is_safe_run_id,
            limit=limit,
        )

    def get_artifact_path(
        self,
        workspace_root: Path,
        skill_name: str,
        run_id: str,
        filename: str,
    ) -> Optional[Path]:
        """Resolve an artifact filename inside a run's artifacts/ folder."""
        if not self.is_safe_run_id(run_id):
            return None
        if not filename or "/" in filename or "\\" in filename or filename in (".", ".."):
            return None
        artifacts_dir = (
            self.runs_root(workspace_root, skill_name) / run_id / "artifacts"
        ).resolve()
        if not artifacts_dir.is_dir():
            return None
        candidate = (artifacts_dir / filename).resolve()
        try:
            candidate.relative_to(artifacts_dir)
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        return candidate

    def delete_artifact(
        self,
        workspace_root: Path,
        skill_name: str,
        run_id: str,
        filename: str,
    ) -> bool:
        path = self.get_artifact_path(workspace_root, skill_name, run_id, filename)
        if path is None:
            return False
        run_dir = self.runs_root(workspace_root, skill_name) / run_id
        artifacts_dir = run_dir / "artifacts"
        try:
            rel = path.relative_to(artifacts_dir.resolve()).as_posix()
        except ValueError:
            rel = path.name
        try:
            path.unlink()
        except OSError:
            return False
        manifest = read_artifact_manifest(run_dir)
        if rel in manifest or path.name in manifest:
            manifest.pop(rel, None)
            manifest.pop(path.name, None)
            write_artifact_manifest(run_dir, manifest)
        return not path.exists()

    def delete_artifacts(
        self,
        workspace_root: Path,
        artifacts: list[dict[str, str]],
    ) -> dict[str, list[dict[str, str]]]:
        deleted: list[dict[str, str]] = []
        missing: list[dict[str, str]] = []
        for item in artifacts:
            ref = {
                "skill": str(item.get("skill") or ""),
                "run_id": str(item.get("run_id") or ""),
                "filename": str(item.get("filename") or ""),
            }
            if self.delete_artifact(
                workspace_root,
                ref["skill"],
                ref["run_id"],
                ref["filename"],
            ):
                deleted.append(ref)
            else:
                missing.append(ref)
        return {"deleted": deleted, "missing": missing}
