"""Persistence and indexing for skill run artifacts."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from src.skills.run_metadata import (
    list_run_artifacts,
    normalize_artifact_products,
    parse_run_envelope,
    read_artifact_manifest,
    resolve_artifact_display_name,
    resolve_artifact_mime,
    slugify_for_filename,
    write_artifact_manifest,
)
from src.skills.chain_contracts import CONTRACT_REGISTRY
from src.skills.run_index import (
    SkillRunIndex,
    list_deliverables_under_base,
    list_runs_under_base,
    read_run_under_base,
)
from src.skills.run_projections import project_run_detail_payload

_SAFE_RUN_ID = re.compile(r"^[0-9]{8}_[0-9]{6}_[a-z0-9_-]+$")
_SAFE_CHAIN_ID = re.compile(r"^[0-9]{8}_[0-9]{6}_[a-z0-9_-]+$")
_TRASH_SAFE_ID = re.compile(r"^[0-9]{8}_[0-9]{6}_[0-9]{6}_[a-z0-9._-]+$")


def _contract_products(skill_name: str) -> list[str]:
    contract = CONTRACT_REGISTRY.get(skill_name)
    if not contract:
        return []
    return sorted(contract.produces)


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


class SkillRunStore:
    """Filesystem store for skill run envelopes, outputs, and artifacts."""

    @staticmethod
    def runs_root(workspace_root: Path, skill_name: str) -> Path:
        return Path(workspace_root) / "skill_runs" / skill_name

    @staticmethod
    def chains_root(workspace_root: Path) -> Path:
        return Path(workspace_root) / "skill_chains"

    def chain_run_dir(self, workspace_root: Path, chain_id: str) -> Path:
        return self.chains_root(workspace_root) / chain_id

    @staticmethod
    def is_safe_run_id(run_id: str) -> bool:
        return bool(_SAFE_RUN_ID.match(run_id))

    @staticmethod
    def is_safe_chain_id(chain_id: str) -> bool:
        return bool(_SAFE_CHAIN_ID.match(chain_id))

    def create_chain_run(
        self,
        *,
        workspace_root: Path,
        name: str,
        prompt: str,
    ) -> tuple[str, Path]:
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%d_%H%M%S")
        slug = slugify_for_filename(name or prompt) or "chain"
        chain_id = f"{ts}_{slug}"
        root = self.chains_root(workspace_root)
        chain_dir = root / chain_id
        suffix = 2
        while chain_dir.exists():
            chain_id = f"{ts}_{slug}_{suffix}"
            chain_dir = root / chain_id
            suffix += 1
        chain_dir.mkdir(parents=True, exist_ok=True)
        return chain_id, chain_dir

    @staticmethod
    def write_chain_run(chain_dir: Path, state: dict[str, Any]) -> None:
        (chain_dir / "chain.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    def get_chain_run(
        self, workspace_root: Path, chain_id: str
    ) -> Optional[dict[str, Any]]:
        if not self.is_safe_chain_id(chain_id):
            return None
        chain_path = self.chain_run_dir(workspace_root, chain_id) / "chain.json"
        if not chain_path.is_file():
            return None
        try:
            payload = json.loads(chain_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        payload.setdefault("chain_id", chain_id)
        return payload

    @classmethod
    def project_run_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        return project_run_detail_payload(payload)

    @classmethod
    def project_chain_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        projected = dict(payload)
        spec = projected.get("spec") or {}
        steps = projected.get("steps") or {}
        projected["step_count"] = len(spec.get("steps") or []) or len(steps)
        resume_step_id = cls._chain_resume_step_id(projected)
        projected["resume_step_id"] = resume_step_id
        projected["can_resume"] = bool(resume_step_id)
        return projected

    def list_chain_runs(
        self, workspace_root: Path, limit: int = 50
    ) -> list[dict[str, Any]]:
        root = self.chains_root(workspace_root)
        if not root.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for chain_dir in root.iterdir():
            if not chain_dir.is_dir() or not self.is_safe_chain_id(chain_dir.name):
                continue
            payload = self.get_chain_run(workspace_root, chain_dir.name)
            if not payload:
                continue
            payload = self.project_chain_payload(payload)
            rows.append(
                {
                    "chain_id": payload.get("chain_id") or chain_dir.name,
                    "name": (payload.get("spec") or {}).get("name") or "skill-chain",
                    "workspace": payload.get("workspace") or "",
                    "status": payload.get("status") or "",
                    "created_at": payload.get("created_at") or "",
                    "updated_at": payload.get("updated_at") or "",
                    "finished_at": payload.get("finished_at") or "",
                    "step_count": payload.get("step_count") or len(payload.get("steps") or {}),
                    "error": payload.get("error") or "",
                    "resume_step_id": payload.get("resume_step_id") or "",
                    "can_resume": bool(payload.get("can_resume")),
                }
            )
        rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
        return rows[:limit]

    @staticmethod
    def _chain_resume_step_id(payload: dict[str, Any]) -> str:
        if payload.get("status") in {"completed", "running"}:
            return ""
        explicit = str(payload.get("resume_step_id") or "").strip()
        if explicit:
            return explicit
        input_request = payload.get("input_request") or {}
        requested = str(
            input_request.get("resume_step_id") or input_request.get("step_id") or ""
        ).strip()
        if requested:
            return requested
        steps = payload.get("steps") or {}
        spec_steps = (payload.get("spec") or {}).get("steps") or []
        ordered_ids = [
            str(step.get("id") or "")
            for step in spec_steps
            if isinstance(step, dict) and step.get("id")
        ]
        ordered_ids.extend(
            step_id for step_id in steps.keys() if step_id not in ordered_ids
        )
        for step_id in ordered_ids:
            step = steps.get(step_id) or {}
            if step.get("status") in {"failed", "partial", "skipped", "pending", "running"}:
                return str(step_id)
        return ""

    def _chain_artifact_index(
        self,
        workspace_root: Path,
    ) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
        root = self.chains_root(workspace_root)
        if not root.is_dir():
            return {}
        index: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for chain_dir in root.iterdir():
            if not chain_dir.is_dir() or not self.is_safe_chain_id(chain_dir.name):
                continue
            payload = self.get_chain_run(workspace_root, chain_dir.name)
            if not payload:
                continue
            payload = self.project_chain_payload(payload)
            spec = payload.get("spec") or {}
            spec_steps = spec.get("steps") or []
            steps = payload.get("steps") or {}
            if not isinstance(steps, dict):
                continue
            step_order = {
                str(step.get("id")): idx
                for idx, step in enumerate(spec_steps)
                if isinstance(step, dict) and step.get("id")
            }
            base = {
                "chain_id": payload.get("chain_id") or chain_dir.name,
                "name": spec.get("name") or "skill-chain",
                "status": payload.get("status") or "",
                "mode": payload.get("mode") or "original",
                "source_chain_id": payload.get("source_chain_id") or "",
                "created_at": payload.get("created_at") or "",
                "updated_at": payload.get("updated_at") or "",
                "finished_at": payload.get("finished_at") or "",
                "error": payload.get("error") or "",
                "step_count": payload.get("step_count") or len(spec_steps) or len(steps),
                "resume_step_id": payload.get("resume_step_id") or "",
                "can_resume": bool(payload.get("can_resume")),
            }
            promoted_keys = {
                (
                    str(ref.get("skill") or ""),
                    str(ref.get("run_id") or ""),
                    str(ref.get("filename") or ""),
                )
                for ref in payload.get("promoted_artifacts") or []
                if isinstance(ref, dict)
            }
            has_explicit_promotion = bool(payload.get("promoted_artifacts") is not None)
            for step_id, step in steps.items():
                if not isinstance(step, dict):
                    continue
                skill = str(step.get("skill") or "")
                run_id = str(step.get("run_id") or "")
                if not skill or not self.is_safe_run_id(run_id):
                    continue
                artifacts = step.get("artifacts") or []
                if not isinstance(artifacts, list):
                    continue
                for artifact in artifacts:
                    if not isinstance(artifact, dict):
                        continue
                    filename = str(
                        artifact.get("filename") or artifact.get("name") or ""
                    )
                    if not filename or "/" in filename or "\\" in filename:
                        continue
                    key = (skill, run_id, filename)
                    surface = "promoted"
                    if has_explicit_promotion:
                        surface = "promoted" if key in promoted_keys else "source"
                    index.setdefault(key, []).append(
                        {
                            **base,
                            "step_id": str(step.get("id") or step_id),
                            "step_status": step.get("status") or "",
                            "step_index": step_order.get(str(step_id), -1),
                            "surface": surface,
                            "run_kind": "chain",
                        }
                    )
        for refs in index.values():
            refs.sort(key=lambda ref: ref.get("created_at", ""), reverse=True)
        return index

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

    def annotate_artifact_products(
        self,
        workspace_root: Path,
        skill_name: str,
        run_id: str,
        products: list[str] | None = None,
    ) -> int:
        """Persist semantic product labels into a run's artifact manifest."""
        if not self.is_safe_run_id(run_id):
            return 0
        product_list = normalize_artifact_products(products or _contract_products(skill_name))
        if not product_list:
            return 0
        run_dir = self.runs_root(workspace_root, skill_name) / run_id
        artifacts_dir = run_dir / "artifacts"
        if not artifacts_dir.is_dir():
            return 0
        manifest = read_artifact_manifest(run_dir)
        changed = 0
        for artifact in sorted(artifacts_dir.iterdir()):
            if not artifact.is_file():
                continue
            rel = artifact.relative_to(artifacts_dir).as_posix()
            entry = dict(manifest.get(rel) or {})
            existing = normalize_artifact_products(entry.get("products"))
            merged = existing[:]
            for product in product_list:
                if product not in merged:
                    merged.append(product)
            if merged != existing:
                entry["products"] = merged
                manifest[rel] = entry
                changed += 1
        if changed:
            write_artifact_manifest(run_dir, manifest)
        return changed

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
        self,
        workspace_root: Path,
        limit: int = 500,
        include_source_chain_artifacts: bool = False,
    ) -> list[dict[str, Any]]:
        rows = SkillRunIndex(Path(workspace_root) / "skill_runs").list_deliverables(
            is_safe_run_id=self.is_safe_run_id,
            limit=limit,
        )
        chain_index = self._chain_artifact_index(workspace_root)
        visible_rows: list[dict[str, Any]] = []
        for row in rows:
            key = (
                str(row.get("skill") or ""),
                str(row.get("run_id") or ""),
                str(row.get("filename") or ""),
            )
            chains = chain_index.get(key) or []
            if chains:
                visible_chains = [chain for chain in chains if chain.get("surface") == "promoted"]
                if not visible_chains and not include_source_chain_artifacts:
                    continue
                row["chains"] = visible_chains or chains
                row["chain"] = (visible_chains or chains)[0]
                row["run_kind"] = "chain"
                row["surface"] = row["chain"].get("surface") or "promoted"
            else:
                row["run_kind"] = "single"
                row["surface"] = "promoted"
            visible_rows.append(row)
        return visible_rows

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
        rel = str(filename or "").replace("\\", "/").strip().strip("/")
        if not rel or ".." in rel.split("/") or rel in {".", ".."}:
            return None
        artifacts_dir = (
            self.runs_root(workspace_root, skill_name) / run_id / "artifacts"
        ).resolve()
        if not artifacts_dir.is_dir():
            return None
        candidate = (artifacts_dir / rel).resolve()
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
