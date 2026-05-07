"""Persistence and indexing for skill run artifacts."""

from __future__ import annotations

import json
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
_TRASH_SAFE_ID = re.compile(r"^[0-9]{8}_[0-9]{6}_[0-9]{6}_[a-z0-9._-]+$")


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

    def _trash_root(self, workspace_root: Path) -> Path:
        return Path(workspace_root) / ".trash" / "studio_artifacts"

    def _trash_item_dir(self, workspace_root: Path, trash_id: str) -> Optional[Path]:
        if not _TRASH_SAFE_ID.fullmatch(trash_id):
            return None
        trash_root = self._trash_root(workspace_root).resolve()
        item_dir = (trash_root / trash_id).resolve()
        try:
            item_dir.relative_to(trash_root)
        except ValueError:
            return None
        return item_dir

    def _trash_meta_path(self, workspace_root: Path, trash_id: str) -> Optional[Path]:
        item_dir = self._trash_item_dir(workspace_root, trash_id)
        if item_dir is None:
            return None
        return item_dir / "meta.json"

    def _read_trash_meta(self, workspace_root: Path, trash_id: str) -> Optional[dict[str, Any]]:
        meta_path = self._trash_meta_path(workspace_root, trash_id)
        if meta_path is None or not meta_path.is_file():
            return None
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        payload["trash_id"] = trash_id
        return payload

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

    @staticmethod
    def _trash_root(workspace_root: Path) -> Path:
        return Path(workspace_root) / ".trash" / "studio_artifacts"

    @staticmethod
    def _run_trash_root(workspace_root: Path) -> Path:
        return Path(workspace_root) / ".trash" / "skill_runs"

    @classmethod
    def _trash_item_dir(cls, workspace_root: Path, trash_id: str) -> Optional[Path]:
        if not _TRASH_SAFE_ID.fullmatch(trash_id):
            return None
        trash_root = cls._trash_root(workspace_root).resolve()
        item_dir = (trash_root / trash_id).resolve()
        try:
            item_dir.relative_to(trash_root)
        except ValueError:
            return None
        return item_dir

    @classmethod
    def _trash_meta_path(cls, workspace_root: Path, trash_id: str) -> Optional[Path]:
        item_dir = cls._trash_item_dir(workspace_root, trash_id)
        if item_dir is None:
            return None
        return item_dir / "meta.json"

    @classmethod
    def _read_trash_meta(cls, workspace_root: Path, trash_id: str) -> Optional[dict[str, Any]]:
        meta_path = cls._trash_meta_path(workspace_root, trash_id)
        if meta_path is None or not meta_path.is_file():
            return None
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        payload["trash_id"] = trash_id
        return payload

    @classmethod
    def _run_trash_item_dir(cls, workspace_root: Path, trash_id: str) -> Optional[Path]:
        if not _TRASH_SAFE_ID.fullmatch(trash_id):
            return None
        trash_root = cls._run_trash_root(workspace_root).resolve()
        item_dir = (trash_root / trash_id).resolve()
        try:
            item_dir.relative_to(trash_root)
        except ValueError:
            return None
        return item_dir

    @classmethod
    def _run_trash_meta_path(cls, workspace_root: Path, trash_id: str) -> Optional[Path]:
        item_dir = cls._run_trash_item_dir(workspace_root, trash_id)
        if item_dir is None:
            return None
        return item_dir / "meta.json"

    @classmethod
    def _read_run_trash_meta(
        cls,
        workspace_root: Path,
        trash_id: str,
    ) -> Optional[dict[str, Any]]:
        meta_path = cls._run_trash_meta_path(workspace_root, trash_id)
        if meta_path is None or not meta_path.is_file():
            return None
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        payload["trash_id"] = trash_id
        return payload

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

    def trash_run(
        self,
        workspace_root: Path,
        skill_name: str,
        run_id: str,
    ) -> Optional[dict[str, Any]]:
        if not self.is_safe_run_id(run_id):
            return None
        run_dir = self.runs_root(workspace_root, skill_name) / run_id
        if not run_dir.is_dir():
            return None
        envelope_path = run_dir / "run.md"
        response_path = run_dir / "response.md"
        meta = (
            parse_run_envelope(envelope_path.read_text(encoding="utf-8"))
            if envelope_path.exists()
            else {}
        )
        deleted_at = datetime.now(timezone.utc).isoformat()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        slug = slugify_for_filename(f"{skill_name}_{run_id}")[:80] or "run"
        trash_id = f"{stamp}_{slug}"
        item_dir = self._run_trash_root(workspace_root) / trash_id
        trashed_run_dir = item_dir / run_id
        item_dir.mkdir(parents=True, exist_ok=False)
        try:
            shutil.move(str(run_dir), str(trashed_run_dir))
        except Exception:
            shutil.rmtree(item_dir, ignore_errors=True)
            return None
        artifact_count = len(list_run_artifacts(trashed_run_dir))
        response_chars = 0
        if response_path.exists():
            try:
                response_chars = response_path.stat().st_size
            except OSError:
                response_chars = 0
        payload = {
            "skill": skill_name,
            "run_id": run_id,
            "prompt_preview": meta.get("prompt_preview") or "",
            "created_at": meta.get("created_at") or "",
            "elapsed_ms": meta.get("elapsed_ms") or 0,
            "response_chars": meta.get("response_chars") or response_chars,
            "artifact_count": artifact_count,
            "deleted_at": deleted_at,
        }
        (item_dir / "meta.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {"trash_id": trash_id, **payload}

    def delete_run(self, workspace_root: Path, skill_name: str, run_id: str) -> bool:
        return self.trash_run(workspace_root, skill_name, run_id) is not None

    def purge_run(self, workspace_root: Path, skill_name: str, run_id: str) -> bool:
        """Hard-delete a run dir without sending it through trash."""
        if not self.is_safe_run_id(run_id):
            return False
        run_dir = self.runs_root(workspace_root, skill_name) / run_id
        if not run_dir.is_dir():
            return False
        try:
            shutil.rmtree(run_dir)
        except OSError:
            return False
        return True

    def purge_trashed_runs(
        self,
        workspace_root: Path,
        *,
        skill_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Hard-delete trashed run dirs. If skill_name is None, purges all."""
        trash_root = self._run_trash_root(workspace_root)
        if not trash_root.is_dir():
            return {"purged": 0, "skipped": 0}
        purged = 0
        skipped = 0
        for item_dir in trash_root.iterdir():
            if not item_dir.is_dir():
                continue
            payload = self._read_run_trash_meta(workspace_root, item_dir.name)
            if skill_name and (not payload or str(payload.get("skill") or "") != skill_name):
                skipped += 1
                continue
            try:
                shutil.rmtree(item_dir)
                purged += 1
            except OSError:
                skipped += 1
        return {"purged": purged, "skipped": skipped}

    def list_trashed_runs(
        self,
        workspace_root: Path,
        *,
        skill_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        trash_root = self._run_trash_root(workspace_root)
        if not trash_root.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for item_dir in trash_root.iterdir():
            if not item_dir.is_dir():
                continue
            payload = self._read_run_trash_meta(workspace_root, item_dir.name)
            if payload is None:
                continue
            if skill_name and str(payload.get("skill") or "") != skill_name:
                continue
            rows.append(payload)
        rows.sort(key=lambda row: str(row.get("deleted_at") or ""), reverse=True)
        return rows[:limit]

    def restore_trashed_runs(
        self,
        workspace_root: Path,
        trash_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        restored: list[dict[str, Any]] = []
        missing: list[dict[str, str]] = []
        conflicts: list[dict[str, Any]] = []
        for trash_id in trash_ids:
            payload = self._read_run_trash_meta(workspace_root, trash_id)
            item_dir = self._run_trash_item_dir(workspace_root, trash_id)
            if payload is None or item_dir is None:
                missing.append({"trash_id": trash_id})
                continue
            skill = str(payload.get("skill") or "")
            run_id = str(payload.get("run_id") or "")
            if not skill or not self.is_safe_run_id(run_id):
                conflicts.append({"trash_id": trash_id, **(payload or {}), "reason": "invalid-metadata"})
                continue
            source_dir = item_dir / run_id
            if not source_dir.is_dir():
                missing.append({"trash_id": trash_id, **payload})
                continue
            target_dir = self.runs_root(workspace_root, skill) / run_id
            if target_dir.exists():
                conflicts.append({"trash_id": trash_id, **payload, "reason": "target-exists"})
                continue
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source_dir), str(target_dir))
            try:
                (item_dir / "meta.json").unlink(missing_ok=True)
            except TypeError:
                meta_path = item_dir / "meta.json"
                if meta_path.exists():
                    meta_path.unlink()
            shutil.rmtree(item_dir, ignore_errors=True)
            restored.append({"trash_id": trash_id, **payload})
        return {"restored": restored, "missing": missing, "conflicts": conflicts}

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

    def trash_artifact(
        self,
        workspace_root: Path,
        skill_name: str,
        run_id: str,
        filename: str,
    ) -> Optional[dict[str, Any]]:
        path = self.get_artifact_path(workspace_root, skill_name, run_id, filename)
        if path is None:
            return None
        run_dir = self.runs_root(workspace_root, skill_name) / run_id
        artifacts_dir = run_dir / "artifacts"
        manifest = read_artifact_manifest(run_dir)
        try:
            rel = path.relative_to(artifacts_dir.resolve()).as_posix()
        except ValueError:
            rel = path.name
        manifest_entry = dict(manifest.get(rel) or manifest.get(path.name) or {})
        deleted_at = datetime.now(timezone.utc).isoformat()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        slug = slugify_for_filename(f"{skill_name}_{run_id}_{filename}")[:80] or "artifact"
        trash_id = f"{stamp}_{slug}"
        item_dir = self._trash_root(workspace_root) / trash_id
        trashed_path = item_dir / path.name
        item_dir.mkdir(parents=True, exist_ok=False)
        try:
            shutil.move(str(path), str(trashed_path))
        except Exception:
            shutil.rmtree(item_dir, ignore_errors=True)
            return None
        meta = {
            "skill": skill_name,
            "run_id": run_id,
            "filename": path.name,
            "display_name": resolve_artifact_display_name(path.name, manifest_entry),
            "mime": resolve_artifact_mime(path.name),
            "size": trashed_path.stat().st_size if trashed_path.exists() else 0,
            "deleted_at": deleted_at,
            "original_rel": rel,
            "manifest_entry": manifest_entry,
        }
        (item_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if rel in manifest or path.name in manifest:
            manifest.pop(rel, None)
            manifest.pop(path.name, None)
            write_artifact_manifest(run_dir, manifest)
        return {"trash_id": trash_id, **meta}

    def trash_artifacts(
        self,
        workspace_root: Path,
        artifacts: list[dict[str, str]],
    ) -> dict[str, list[dict[str, Any]]]:
        trashed: list[dict[str, Any]] = []
        missing: list[dict[str, str]] = []
        for item in artifacts:
            ref = {
                "skill": str(item.get("skill") or ""),
                "run_id": str(item.get("run_id") or ""),
                "filename": str(item.get("filename") or ""),
            }
            moved = self.trash_artifact(
                workspace_root,
                ref["skill"],
                ref["run_id"],
                ref["filename"],
            )
            if moved is None:
                missing.append(ref)
            else:
                trashed.append(moved)
        return {"trashed": trashed, "missing": missing}

    def list_trashed_artifacts(
        self,
        workspace_root: Path,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        trash_root = self._trash_root(workspace_root)
        if not trash_root.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for item_dir in trash_root.iterdir():
            if not item_dir.is_dir():
                continue
            payload = self._read_trash_meta(workspace_root, item_dir.name)
            if payload is None:
                continue
            rows.append(payload)
        rows.sort(key=lambda row: str(row.get("deleted_at") or ""), reverse=True)
        return rows[:limit]

    def purge_trashed_artifacts(self, workspace_root: Path) -> dict[str, int]:
        trash_root = self._trash_root(workspace_root)
        if not trash_root.is_dir():
            return {"purged": 0, "skipped": 0}
        purged = 0
        skipped = 0
        for item_dir in trash_root.iterdir():
            if not item_dir.is_dir():
                continue
            try:
                shutil.rmtree(item_dir)
                purged += 1
            except OSError:
                skipped += 1
        return {"purged": purged, "skipped": skipped}

    def restore_trashed_artifacts(
        self,
        workspace_root: Path,
        trash_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        restored: list[dict[str, Any]] = []
        missing: list[dict[str, str]] = []
        conflicts: list[dict[str, Any]] = []
        for trash_id in trash_ids:
            payload = self._read_trash_meta(workspace_root, trash_id)
            item_dir = self._trash_item_dir(workspace_root, trash_id)
            if payload is None or item_dir is None:
                missing.append({"trash_id": trash_id})
                continue
            skill = str(payload.get("skill") or "")
            run_id = str(payload.get("run_id") or "")
            filename = str(payload.get("filename") or "")
            if not self.is_safe_run_id(run_id) or not skill or not filename:
                conflicts.append({"trash_id": trash_id, **payload, "reason": "invalid-metadata"})
                continue
            source_path = item_dir / filename
            if not source_path.is_file():
                missing.append({"trash_id": trash_id, **payload})
                continue
            run_dir = self.runs_root(workspace_root, skill) / run_id
            artifacts_dir = run_dir / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            target = artifacts_dir / filename
            if target.exists():
                conflicts.append({"trash_id": trash_id, **payload, "reason": "target-exists"})
                continue
            shutil.move(str(source_path), str(target))
            manifest = read_artifact_manifest(run_dir)
            original_rel = str(payload.get("original_rel") or filename)
            manifest_entry = payload.get("manifest_entry")
            if isinstance(manifest_entry, dict) and manifest_entry:
                manifest[original_rel] = manifest_entry
                write_artifact_manifest(run_dir, manifest)
            try:
                (item_dir / "meta.json").unlink(missing_ok=True)
            except TypeError:
                meta_path = item_dir / "meta.json"
                if meta_path.exists():
                    meta_path.unlink()
            shutil.rmtree(item_dir, ignore_errors=True)
            restored.append({"trash_id": trash_id, **payload})
        return {"restored": restored, "missing": missing, "conflicts": conflicts}
