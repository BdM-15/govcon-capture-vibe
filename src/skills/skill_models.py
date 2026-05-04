"""Shared skill data models and minimal SKILL.md frontmatter parser."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

_FRONTMATTER_FENCE = "---"
_SPEC_TOP_LEVEL = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
_LEGACY_TOP_LEVEL = {"category", "version", "upstream", "status"}
_KNOWN_KEYS = _SPEC_TOP_LEVEL | _LEGACY_TOP_LEVEL


@dataclass
class SkillFrontmatter:
    """Parsed YAML frontmatter from a SKILL.md file."""

    name: str
    description: str
    category: str = "other"
    version: str = "0.0.0"
    license: str = ""
    upstream: str = ""
    status: str = ""
    compatibility: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def runtime_mode(self) -> str:
        raw = str(self.metadata.get("runtime", "")).strip().lower()
        return "tools" if raw == "tools" else "legacy"

    @property
    def required_mcps(self) -> list[str]:
        raw = self.metadata.get("mcps")
        if raw is None:
            return []
        if isinstance(raw, str):
            return [raw.strip()] if raw.strip() else []
        if isinstance(raw, list):
            return [str(value).strip() for value in raw if str(value).strip()]
        return []


@dataclass
class Skill:
    """A discovered or installed skill."""

    name: str
    path: str
    skill_md_path: str
    frontmatter: SkillFrontmatter
    body_md: str
    has_scripts: bool = False
    has_templates: bool = False
    has_assets: bool = False
    has_references: bool = False
    has_evals: bool = False
    installed_at: str = ""
    last_invoked_at: str = ""
    source: str = "builtin"
    source_url: str = ""

    def to_summary(self) -> dict[str, Any]:
        fm = self.frontmatter
        meta = fm.metadata or {}
        personas_primary_raw = meta.get("personas_primary")
        personas_primary = (
            str(personas_primary_raw).strip()
            if personas_primary_raw not in (None, "", "None")
            else "none"
        )
        personas_secondary_raw = meta.get("personas_secondary", []) or []
        if isinstance(personas_secondary_raw, str):
            personas_secondary = [personas_secondary_raw.strip()] if personas_secondary_raw.strip() else []
        elif isinstance(personas_secondary_raw, list):
            personas_secondary = [str(value).strip() for value in personas_secondary_raw if str(value).strip()]
        else:
            personas_secondary = []
        shipley_phases_raw = meta.get("shipley_phases", []) or []
        if isinstance(shipley_phases_raw, str):
            shipley_phases = [shipley_phases_raw.strip()] if shipley_phases_raw.strip() else []
        elif isinstance(shipley_phases_raw, list):
            shipley_phases = [str(value).strip() for value in shipley_phases_raw if str(value).strip()]
        else:
            shipley_phases = []
        capability_raw = meta.get("capability")
        capability = str(capability_raw).strip() if capability_raw else ""
        return {
            "name": self.name,
            "description": fm.description,
            "category": fm.category,
            "version": fm.version,
            "license": fm.license,
            "upstream": fm.upstream,
            "status": fm.status,
            "has_scripts": self.has_scripts,
            "has_templates": self.has_templates,
            "has_assets": self.has_assets,
            "has_references": self.has_references,
            "has_evals": self.has_evals,
            "runtime_mode": fm.runtime_mode,
            "source": self.source,
            "source_url": self.source_url,
            "installed_at": self.installed_at,
            "last_invoked_at": self.last_invoked_at,
            "personas_primary": personas_primary,
            "personas_secondary": personas_secondary,
            "shipley_phases": shipley_phases,
            "capability": capability,
        }


@dataclass
class SkillInvocationResult:
    """Returned by SkillManager.invoke."""

    skill: str
    workspace: str
    response: str
    entities_used: list[str]
    warnings: list[str]
    elapsed_ms: int
    prompt_tokens_estimate: int
    run_id: str = ""
    run_dir: str = ""


@dataclass
class SkillRunSummary:
    """Lightweight summary of a persisted skill run."""

    run_id: str
    skill: str
    workspace: str
    created_at: str
    elapsed_ms: int
    prompt_preview: str
    response_chars: int
    entities_used: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_scalar(val: str) -> Any:
    s = val.strip()
    if not s:
        return ""
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    low = s.lower()
    if low in {"true", "false"}:
        return low == "true"
    if low in {"null", "none", "~"}:
        return None
    try:
        if "." not in s and "e" not in low:
            return int(s)
        return float(s)
    except ValueError:
        return s


def _parse_inline_list(val: str) -> list[Any]:
    s = val.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_coerce_scalar(part) for part in re.split(r"\s*,\s*", inner)]
    return [_coerce_scalar(part) for part in s.split() if part]


def parse_frontmatter(text: str) -> tuple[SkillFrontmatter, str]:
    """Split a SKILL.md into frontmatter and body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return SkillFrontmatter(name="", description=""), text

    end_idx = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == _FRONTMATTER_FENCE:
            end_idx = idx
            break
    if end_idx == -1:
        logger.warning("Frontmatter fence not closed; treating as no frontmatter")
        return SkillFrontmatter(name="", description=""), text

    front_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1 :]).lstrip("\n")

    parsed: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    in_metadata_block = False
    metadata_indent = -1
    pending_list_key: Optional[str] = None
    pending_list_indent = -1
    pending_list_target: Optional[dict[str, Any]] = None

    for raw in front_lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        stripped = raw.lstrip()
        indent = len(raw) - len(stripped)

        if pending_list_key is not None and stripped.startswith("-") and indent > pending_list_indent:
            item = stripped[1:].strip()
            if pending_list_target is not None:
                pending_list_target.setdefault(pending_list_key, []).append(_coerce_scalar(item))
            continue

        pending_list_key = None
        pending_list_target = None

        if in_metadata_block and indent > metadata_indent:
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$", stripped)
            if not match:
                extras.setdefault("_unparsed", []).append(raw)
                continue
            key, val = match.group(1), match.group(2)
            if not val.strip():
                pending_list_key = key
                pending_list_indent = indent
                pending_list_target = metadata
                metadata.setdefault(key, [])
                continue
            if val.strip().startswith("["):
                metadata[key] = _parse_inline_list(val)
            else:
                metadata[key] = _coerce_scalar(val)
            continue

        in_metadata_block = False
        metadata_indent = -1

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$", raw)
        if not match:
            extras.setdefault("_unparsed", []).append(raw)
            continue
        key, val = match.group(1), match.group(2)

        if key == "metadata" and not val.strip():
            in_metadata_block = True
            metadata_indent = indent
            continue

        if key == "metadata" and val.strip().startswith("{"):
            inner = val.strip()[1:-1].strip() if val.strip().endswith("}") else ""
            for pair in re.split(r"\s*,\s*", inner) if inner else []:
                if ":" in pair:
                    key2, value2 = pair.split(":", 1)
                    metadata[key2.strip()] = _coerce_scalar(value2)
            continue

        if key == "allowed-tools":
            if not val.strip():
                pending_list_key = key
                pending_list_indent = indent
                pending_list_target = parsed
                parsed.setdefault(key, [])
            else:
                parsed[key] = _parse_inline_list(val) if val.strip().startswith("[") else val.strip().split()
            continue

        if not val.strip():
            pending_list_key = key
            pending_list_indent = indent
            pending_list_target = parsed
            parsed.setdefault(key, [])
            continue

        coerced = _coerce_scalar(val)
        if key in _KNOWN_KEYS:
            parsed[key] = coerced
        else:
            extras[key] = coerced

    def _meta_or_top(key: str, default: Any) -> Any:
        if key in metadata:
            return metadata[key]
        return parsed.get(key, default)

    frontmatter = SkillFrontmatter(
        name=str(parsed.get("name", "")),
        description=str(parsed.get("description", "")),
        category=str(_meta_or_top("category", "other")),
        version=str(_meta_or_top("version", "0.0.0")),
        license=str(parsed.get("license", "")),
        upstream=str(_meta_or_top("upstream", "")),
        status=str(_meta_or_top("status", "")),
        compatibility=str(parsed.get("compatibility", "")),
        metadata=metadata,
        allowed_tools=list(parsed.get("allowed-tools", []) or []),
        extras=extras,
    )
    return frontmatter, body