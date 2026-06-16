"""Fingerprint readiness gate/skill code so server can prove it matches workspace."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_WATCH_REL_PATHS = (
    "src/skills/readiness_handoff_gates.py",
    "src/skills/platform_step_finalize.py",
    "src/skills/readiness_handoff_models.py",
    "src/skills/readiness_solo_invoke.py",
    "src/skills/handoff_quality.py",
    "src/skills/pains_handoff_repair.py",
    "src/skills/modernization_handoff_repair.py",
    "src/skills/tea_leaves_handoff_repair.py",
    "src/skills/win_themes_handoff_repair.py",
    "src/skills/eval_handoff_repair.py",
)


def _git_head(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "no-git"
    if result.returncode != 0:
        return "no-git"
    return (result.stdout or "").strip() or "no-git"


def compute_server_code_fingerprint(*, repo_root: Path | None = None) -> str:
    """Stable short hash: git HEAD + mtimes of readiness gate/skill paths."""
    root = repo_root or _REPO_ROOT
    parts = [_git_head(root)]
    for rel in _WATCH_REL_PATHS:
        path = root / rel
        if path.is_file():
            parts.append(f"{rel}:{int(path.stat().st_mtime_ns)}")
    skill_root = root / ".github" / "skills"
    if skill_root.is_dir():
        for skill_dir in sorted(skill_root.glob("readiness-frame-*")):
            skill_md = skill_dir / "SKILL.md"
            tools_py = next(skill_dir.glob("*_handoff_tools.py"), None)
            if skill_md.is_file():
                parts.append(f"{skill_md.relative_to(root)}:{int(skill_md.stat().st_mtime_ns)}")
            if tools_py is not None and tools_py.is_file():
                parts.append(f"{tools_py.relative_to(root)}:{int(tools_py.stat().st_mtime_ns)}")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]