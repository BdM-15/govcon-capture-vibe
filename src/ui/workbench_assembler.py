"""Assemble the Capture Workbench SPA from a thin shell and view fragments."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_VIEW_MARKER_RE = re.compile(r"<!--\s*THESEUS_VIEW:(\w+)\s*-->")

# Order must match navigation; used by contract tests and assembly validation.
WORKBENCH_VIEW_IDS = (
    "dashboard",
    "documents",
    "graph",
    "chat",
    "intel",
    "prompts",
    "skills",
    "chains",
    "studio",
    "activity",
    "settings",
)

_STATIC_ROOT = Path(__file__).resolve().parent / "static"


def view_fragment_path(static_root: Path, view_id: str) -> Path:
    return static_root / "views" / f"{view_id}-view.html"


@lru_cache(maxsize=4)
def assemble_workbench_html(static_root: str | None = None) -> str:
    """Stitch ``index.shell.html`` by replacing view markers with fragment files."""
    root = Path(static_root) if static_root else _STATIC_ROOT
    shell_path = root / "index.shell.html"
    if not shell_path.is_file():
        legacy = root / "index.html"
        if legacy.is_file():
            return legacy.read_text(encoding="utf-8-sig")
        raise FileNotFoundError(f"Workbench shell missing: {shell_path}")

    shell = shell_path.read_text(encoding="utf-8-sig")
    views_dir = root / "views"
    missing = [
        view_id
        for view_id in WORKBENCH_VIEW_IDS
        if not view_fragment_path(root, view_id).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            f"Missing workbench view fragments under {views_dir}: {', '.join(missing)}"
        )

    def _inject(match: re.Match[str]) -> str:
        view_id = match.group(1)
        fragment = view_fragment_path(root, view_id)
        if not fragment.is_file():
            raise FileNotFoundError(f"Unknown workbench view marker: {view_id}")
        return fragment.read_text(encoding="utf-8-sig")

    assembled = _VIEW_MARKER_RE.sub(_inject, shell)
    if _VIEW_MARKER_RE.search(assembled):
        raise RuntimeError("Workbench shell still contains unresolved THESEUS_VIEW markers")
    return assembled