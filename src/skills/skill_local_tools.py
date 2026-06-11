"""Load co-located Python tool modules from a skill directory."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable, Optional


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


@dataclass(frozen=True)
class SkillToolsHooks:
    """Optional platform hooks declared in a skill's co-located ``*_tools.py`` modules."""

    artifact_continue: Optional[Callable[[Path], Optional[str]]] = None
    validate_run: Optional[Callable[..., list[str]]] = None
    write_depth_audit: Optional[Callable[[Path, list[str]], Path]] = None


def resolve_skill_tools_hooks(skill_dir: Path) -> SkillToolsHooks:
    """Discover platform hooks from any ``*_tools.py`` module in a skill folder."""
    root = Path(skill_dir).resolve()
    artifact_continue = None
    validate_run = None
    write_depth_audit = None

    for path in sorted(root.glob("*_tools.py")):
        try:
            module = load_skill_tool_module(root, path.stem)
        except (FileNotFoundError, ImportError):
            continue
        if artifact_continue is None:
            candidate = getattr(module, "artifact_continue_message", None)
            if callable(candidate):
                artifact_continue = candidate
        if validate_run is None:
            candidate = getattr(module, "validate_skill_run", None)
            if callable(candidate):
                validate_run = candidate
        if write_depth_audit is None:
            candidate = getattr(module, "write_depth_audit", None)
            if callable(candidate):
                write_depth_audit = candidate

    return SkillToolsHooks(
        artifact_continue=artifact_continue,
        validate_run=validate_run,
        write_depth_audit=write_depth_audit,
    )


def resolve_artifact_continue_fn(
    skill_dir: Path,
) -> Optional[Callable[[Path], Optional[str]]]:
    """Return ``artifact_continue_message`` if the skill declares one."""
    return resolve_skill_tools_hooks(skill_dir).artifact_continue


def resolve_skill_run_validator(
    skill_dir: Path,
) -> Optional[Callable[..., list[str]]]:
    """Return ``validate_skill_run`` if the skill declares one."""
    return resolve_skill_tools_hooks(skill_dir).validate_run