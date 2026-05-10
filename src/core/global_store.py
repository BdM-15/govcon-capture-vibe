"""Thin file-backed storage facade for Ariadne's Thread global markdown."""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

_GLOBAL_BUCKETS = frozenset({"inbox", "notes", "llm-wiki", "intel"})
_SAFE_WORKSPACE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_PROMOTION_MANIFEST = ".ariadne_promotions.json"


def _default_root() -> Path:
    return (Path(__file__).resolve().parents[2] / "global").resolve()


def _default_workspace_root() -> Path:
    return (Path(__file__).resolve().parents[2] / "rag_storage").resolve()


class GlobalStore:
    """Safe read/write/list/search facade over repo-local `global/` markdown."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root).resolve() if root is not None else _default_root()
        self.root.mkdir(parents=True, exist_ok=True)
        for bucket in _GLOBAL_BUCKETS:
            (self.root / bucket).mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative_path: str | Path) -> Path:
        raw = str(relative_path or "").replace("\\", "/").strip("/")
        if not raw:
            return self.root
        resolved = (self.root / raw).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Path escapes global root") from exc
        return resolved

    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
        if not text.startswith("---\n"):
            return {}, text

        lines = text.splitlines()
        closing_index = next(
            (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
            None,
        )
        if closing_index is None:
            return {}, text

        frontmatter_text = "\n".join(lines[1:closing_index])
        body = "\n".join(lines[closing_index + 1 :]).lstrip("\n")
        payload = yaml.safe_load(frontmatter_text) or {}
        return payload if isinstance(payload, dict) else {}, body

    @staticmethod
    def _preview(body: str, *, limit: int = 200) -> str:
        for line in body.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped[:limit]
        return ""

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: cls._json_safe(inner) for key, inner in value.items()}
        if isinstance(value, list):
            return [cls._json_safe(inner) for inner in value]
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _promotion_id(source_relative: str) -> str:
        return hashlib.sha256(source_relative.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _workspace_dir(workspace_root: str | Path | None, workspace: str) -> Path:
        if not _SAFE_WORKSPACE.fullmatch(workspace or ""):
            raise ValueError(f"Invalid workspace name: {workspace}")
        workspace_base = (
            Path(workspace_root).resolve() if workspace_root is not None else _default_workspace_root()
        )
        return workspace_base / workspace

    @staticmethod
    def _promotion_manifest_path(workspace_dir: Path) -> Path:
        return workspace_dir / "sources" / _PROMOTION_MANIFEST

    @classmethod
    def _read_promotion_manifest(cls, workspace_dir: Path) -> dict[str, Any]:
        manifest_path = cls._promotion_manifest_path(workspace_dir)
        if not manifest_path.is_file():
            return {"version": 1, "promotions": []}
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "promotions": []}
        if not isinstance(payload, dict):
            return {"version": 1, "promotions": []}
        promotions = payload.get("promotions")
        if not isinstance(promotions, list):
            promotions = []
        return {"version": int(payload.get("version") or 1), "promotions": promotions}

    @classmethod
    def _write_promotion_manifest(cls, workspace_dir: Path, manifest: dict[str, Any]) -> Path:
        manifest_path = cls._promotion_manifest_path(workspace_dir)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest_path

    @staticmethod
    def _find_promotion(manifest: dict[str, Any], promotion_id: str) -> dict[str, Any] | None:
        for record in manifest.get("promotions") or []:
            if isinstance(record, dict) and record.get("id") == promotion_id:
                return record
        return None

    def _markdown_files(self, base: Path) -> list[Path]:
        if not base.exists():
            return []
        if base.is_file():
            return [base] if base.suffix.lower() == ".md" else []
        return sorted(
            (path for path in base.rglob("*.md") if path.is_file()),
            key=lambda path: (path.stat().st_mtime_ns, str(path)),
            reverse=True,
        )

    def _entry(self, path: Path) -> dict[str, Any]:
        relative = path.relative_to(self.root).as_posix()
        text = path.read_text(encoding="utf-8")
        frontmatter, body = self._parse_frontmatter(text)
        parts = Path(relative).parts
        bucket = parts[0] if parts else ""
        return {
            "path": relative,
            "bucket": bucket,
            "name": path.name,
            "stem": path.stem,
            "frontmatter": self._json_safe(frontmatter),
            "preview": self._preview(body),
            "content": body,
            "modified_at": path.stat().st_mtime,
        }

    def read(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    def write(self, path: str, content: str) -> Path:
        target = self._resolve(path)
        if target.suffix.lower() != ".md":
            raise ValueError("GlobalStore only writes markdown files")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def list(self, prefix: str = "") -> list[dict[str, Any]]:
        base = self._resolve(prefix)
        return [self._entry(path) for path in self._markdown_files(base)]

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        needle = (query or "").strip().casefold()
        if not needle:
            return []

        matches: list[dict[str, Any]] = []
        for path in self._markdown_files(self.root):
            entry = self._entry(path)
            haystack = f"{entry['path']}\n{entry['content']}".casefold()
            if needle not in haystack:
                continue
            entry["score"] = (
                2 if needle in entry["path"].casefold() else 0
            ) + haystack.count(needle)
            matches.append(entry)

        matches.sort(
            key=lambda entry: (entry.get("score", 0), entry.get("modified_at", 0), entry["path"]),
            reverse=True,
        )
        return matches[:limit]

    def promote(
        self,
        path: str,
        *,
        workspace: str,
        workspace_root: str | Path | None = None,
    ) -> dict[str, Any]:
        source = self._resolve(path)
        source_relative = source.relative_to(self.root).as_posix()
        workspace_dir = self._workspace_dir(workspace_root, workspace)
        source_text = source.read_text(encoding="utf-8")
        digest = self._sha256(source_text)
        target = workspace_dir / "sources" / source.name
        target_relative = target.relative_to(workspace_dir).as_posix()
        manifest = self._read_promotion_manifest(workspace_dir)
        promotion_id = self._promotion_id(source_relative)
        record = self._find_promotion(manifest, promotion_id)

        if target.exists() and self._sha256(target.read_text(encoding="utf-8")) != digest:
            raise ValueError(f"Target already exists with different content: {target}")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source_text, encoding="utf-8")

        now = self._utc_now()
        next_record = {
            "id": promotion_id,
            "source": source_relative,
            "workspace": workspace,
            "target": target_relative,
            "source_sha256": digest,
            "target_sha256": digest,
            "promoted_at": record.get("promoted_at") if record else now,
            "updated_at": now,
            "active": True,
            "ingestion_status": (record or {}).get("ingestion_status") or "pending",
            "doc_id": (record or {}).get("doc_id"),
        }
        if record is None:
            manifest["promotions"].append(next_record)
        else:
            record.clear()
            record.update(next_record)
        manifest_path = self._write_promotion_manifest(workspace_dir, manifest)

        return {
            "promotion_id": promotion_id,
            "source": source_relative,
            "workspace": workspace,
            "target": str(target),
            "target_relative": target_relative,
            "manifest": str(manifest_path),
            "ingestion_status": next_record["ingestion_status"],
        }

    def list_promotions(
        self,
        *,
        workspace: str,
        workspace_root: str | Path | None = None,
        active_only: bool = False,
    ) -> list[dict[str, Any]]:
        workspace_dir = self._workspace_dir(workspace_root, workspace)
        promotions = [
            dict(record)
            for record in self._read_promotion_manifest(workspace_dir).get("promotions") or []
            if isinstance(record, dict)
        ]
        if active_only:
            promotions = [record for record in promotions if record.get("active")]
        promotions.sort(key=lambda record: str(record.get("updated_at") or ""), reverse=True)
        return promotions

    def update_promotion_ingestion(
        self,
        path: str,
        *,
        workspace: str,
        ingestion_status: str,
        workspace_root: str | Path | None = None,
        doc_id: str | None = None,
        refresh_result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        source = self._resolve(path)
        source_relative = source.relative_to(self.root).as_posix()
        workspace_dir = self._workspace_dir(workspace_root, workspace)
        manifest = self._read_promotion_manifest(workspace_dir)
        promotion_id = self._promotion_id(source_relative)
        record = self._find_promotion(manifest, promotion_id)
        if record is None or not record.get("active"):
            raise FileNotFoundError(f"Promotion not found: {source_relative} -> {workspace}")

        now = self._utc_now()
        record["ingestion_status"] = ingestion_status
        record["updated_at"] = now
        record["last_refresh_at"] = now
        if doc_id is not None:
            record["doc_id"] = doc_id
        if refresh_result is not None:
            record["last_refresh_result"] = self._json_safe(refresh_result)
        if error:
            record["ingestion_error"] = error
        else:
            record.pop("ingestion_error", None)

        self._write_promotion_manifest(workspace_dir, manifest)
        return dict(record)

    def unpromote(
        self,
        path: str,
        *,
        workspace: str,
        workspace_root: str | Path | None = None,
        delete_target: bool = True,
    ) -> dict[str, Any]:
        source = self._resolve(path)
        source_relative = source.relative_to(self.root).as_posix()
        workspace_dir = self._workspace_dir(workspace_root, workspace)
        manifest = self._read_promotion_manifest(workspace_dir)
        promotion_id = self._promotion_id(source_relative)
        record = self._find_promotion(manifest, promotion_id)
        if record is None or not record.get("active"):
            raise FileNotFoundError(f"Promotion not found: {source_relative} -> {workspace}")

        target = (workspace_dir / str(record.get("target") or "")).resolve()
        try:
            target.relative_to(workspace_dir.resolve())
        except ValueError as exc:
            raise ValueError("Promoted target escapes workspace root") from exc

        deleted_target = False
        if delete_target and target.exists():
            current_digest = self._sha256(target.read_text(encoding="utf-8"))
            if current_digest != record.get("target_sha256"):
                raise ValueError(f"Promoted target changed; refusing to delete: {target}")
            target.unlink()
            deleted_target = True

        now = self._utc_now()
        record["active"] = False
        record["revoked_at"] = now
        record["updated_at"] = now
        record["deleted_target"] = deleted_target
        manifest_path = self._write_promotion_manifest(workspace_dir, manifest)
        return {
            "promotion_id": promotion_id,
            "source": source_relative,
            "workspace": workspace,
            "target": str(target),
            "target_relative": str(record.get("target") or ""),
            "manifest": str(manifest_path),
            "deleted_target": deleted_target,
            "active": False,
        }


__all__ = ["GlobalStore"]