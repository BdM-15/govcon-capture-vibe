"""Disk-walking index for persisted skill runs under ``skill_runs/``."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from src.skills.chain_contracts import CONTRACT_REGISTRY
from src.skills.run_metadata import (
    list_run_artifacts,
    list_tool_outputs,
    normalize_artifact_products,
    parse_run_envelope,
    read_artifact_manifest,
    read_run_metadata,
    read_run_transcript,
    resolve_artifact_mime,
)
from src.skills.run_projections import project_run_summary_payload
from src.skills.artifact_labels import (
    derive_run_content_title,
    humanize_run_label,
    maybe_enrich_display_name_with_prompt,
    resolve_studio_display_name,
)
from src.skills.studio_surfaces import (
    iter_studio_deliverable_paths,
    validate_deck_index,
)


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
        pending: list[dict[str, Any]] = []
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
            content_title = derive_run_content_title(skill_name, run_dir)
            run_label = humanize_run_label(run_dir.name)

            for rel, artifact in iter_studio_deliverable_paths(artifacts_dir):
                if skill_name == "huashu-design" and rel.lower().endswith(".docx"):
                    continue
                try:
                    stat = artifact.stat()
                except OSError:
                    continue
                manifest_entry = manifest.get(rel) or manifest.get(artifact.name)
                products = normalize_artifact_products(
                    (manifest_entry or {}).get("products")
                ) or _contract_products(skill_name)
                deck = (manifest_entry or {}).get("deck_completeness") or {}
                if (
                    skill_name == "huashu-design"
                    and rel.endswith("index.html")
                    and not deck
                ):
                    deck = validate_deck_index(artifact)
                display_name = resolve_studio_display_name(
                    skill_name=skill_name,
                    run_dir=run_dir,
                    artifact_rel=rel,
                    manifest_entry=manifest_entry,
                    content_title=content_title,
                )
                pending.append(
                    {
                        "skill": skill_name,
                        "run_id": run_dir.name,
                        "run_label": run_label,
                        "filename": rel,
                        "display_name": display_name,
                        "mime": resolve_artifact_mime(artifact.name),
                        "size": stat.st_size,
                        "created_at": created_at
                        or datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                        "title": title,
                        "ext": artifact.suffix.lstrip(".").lower(),
                        "products": products,
                        "deck_complete": deck.get("complete"),
                        "deck_slides_found": deck.get("found"),
                        "deck_slides_expected": deck.get("expected"),
                        "_run_dir": run_dir,
                    }
                )

        collision_counts = Counter(
            (row["skill"], str(row.get("display_name") or "").lower())
            for row in pending
        )
        rows: list[dict[str, Any]] = []
        for row in pending:
            run_dir = row.pop("_run_dir")
            force_variant = collision_counts[
                (row["skill"], str(row.get("display_name") or "").lower())
            ] > 1
            row["display_name"] = maybe_enrich_display_name_with_prompt(
                str(row.get("display_name") or ""),
                skill_name=str(row.get("skill") or ""),
                run_dir=run_dir,
                artifact_rel=str(row.get("filename") or ""),
                force=force_variant,
            )
            rows.append(row)

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