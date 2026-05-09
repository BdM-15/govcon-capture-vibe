"""Thin file-backed storage facade for Ariadne's Thread global markdown."""

from __future__ import annotations

from datetime import date, datetime
import re
from pathlib import Path
from typing import Any

import yaml

_GLOBAL_BUCKETS = frozenset({"inbox", "notes", "llm-wiki", "intel"})
_SAFE_WORKSPACE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


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
    ) -> dict[str, str]:
        if not _SAFE_WORKSPACE.fullmatch(workspace or ""):
            raise ValueError(f"Invalid workspace name: {workspace}")

        source = self._resolve(path)
        workspace_base = (
            Path(workspace_root).resolve() if workspace_root is not None else _default_workspace_root()
        )
        target = workspace_base / workspace / "sources" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        return {
            "source": source.relative_to(self.root).as_posix(),
            "workspace": workspace,
            "target": str(target),
        }


__all__ = ["GlobalStore"]