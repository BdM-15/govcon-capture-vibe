"""Project Theseus — Agent Skills Platform.

Discovers, installs, and invokes skills authored to the agentskills.io
standard. Skills live in ``.github/skills/`` (the official location) and are
mirrored conceptually under ``theseus-skills/`` for repo discoverability.

The manager has zero new third-party dependencies — it parses YAML
frontmatter with a small inline parser to avoid pulling in ``PyYAML``.
"""

from __future__ import annotations

from .manager import SkillManager, get_skill_manager
from .skill_models import (
    Skill,
    SkillFrontmatter,
    SkillInvocationResult,
    SkillRunSummary,
)

__all__ = [
    "Skill",
    "SkillFrontmatter",
    "SkillInvocationResult",
    "SkillManager",
    "SkillRunSummary",
    "get_skill_manager",
]
