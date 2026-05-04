"""Persistence and indexing for skill run artifacts."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.skills.run_metadata import (
    STUDIO_EXTRA_MIME,
    list_run_artifacts,
    list_tool_outputs,
    parse_run_envelope,
    read_run_metadata,
    read_run_transcript,
    resolve_artifact_mime,
    slugify_for_filename,
)
from src.skills.run_store_helpers import (
    build_legacy_run_envelope,
    build_tools_run_envelope,
    list_deliverables_under_base,
    list_runs_under_base,
)

_SAFE_RUN_ID = re.compile(r"^[0-9]{8}_[0-9]{6}_[a-z0-9_-]+$")


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
        return list_runs_under_base(
            Path(workspace_root) / "skill_runs",
            skill_name=skill_name,
            limit=limit,
        )

    def get_run(
        self, workspace_root: Path, skill_name: str, run_id: str
    ) -> Optional[dict[str, Any]]:
        """Return the full content of a single persisted run, or None."""
        if not self.is_safe_run_id(run_id):
            return None
        run_dir = self.runs_root(workspace_root, skill_name) / run_id
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
        artifacts = list_run_artifacts(run_dir)
        transcript = read_run_transcript(run_dir)
        tool_outputs = list_tool_outputs(run_dir)
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
            "artifacts": artifacts,
            "transcript": transcript,
            "tool_outputs": tool_outputs,
        }

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
        return list_deliverables_under_base(
            Path(workspace_root) / "skill_runs",
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
