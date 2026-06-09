"""Disk-walking index for persisted skill runs under ``skill_runs/``."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from src.skills.chain_contracts import CONTRACT_REGISTRY
from src.skills.run_metadata import (
    is_studio_deliverable,
    list_run_artifacts,
    list_tool_outputs,
    normalize_artifact_products,
    parse_run_envelope,
    read_artifact_manifest,
    read_run_metadata,
    read_run_transcript,
    resolve_artifact_display_name,
    resolve_artifact_mime,
)
from src.skills.run_projections import project_run_summary_payload


def _contract_products(skill_name: str) -> list[str]:
    contract = CONTRACT_REGISTRY.get(skill_name)
    if not contract:
        return []
    return sorted(contract.produces)


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
            response = ""
            if response_path.exists():
                try:
                    response = response_path.read_text(encoding="utf-8")
                except OSError:
                    response = ""
            runs.append(project_run_summary_payload(meta, response))
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
            "artifacts": list_run_artifacts(
                run_dir,
                default_products=_contract_products(skill_name),
            ),
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
                products = normalize_artifact_products(
                    (manifest.get(rel) or {}).get("products")
                ) or _contract_products(skill_name)
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
                        "products": products,
                    }
                )

        rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
        return rows[:limit]


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