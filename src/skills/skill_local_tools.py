"""Load co-located Python tool modules from a skill directory."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_skill_tool_module(skill_dir: Path, stem: str) -> ModuleType:
    """Import ``<skill_dir>/<stem>.py`` as a one-off module."""
    path = Path(skill_dir).resolve() / f"{stem}.py"
    if not path.is_file():
        raise FileNotFoundError(f"Skill tool module not found: {path}")
    module_name = f"theseus_skill_tool_{path.parent.name}_{stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load skill tool module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module