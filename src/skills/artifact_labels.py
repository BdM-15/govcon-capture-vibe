"""Human-readable Studio labels derived from run content, not skill slugs."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from src.skills.run_metadata import (
    humanize_artifact_name,
    read_run_metadata,
    sanitize_artifact_display_name,
)

_RUN_ID_RE = re.compile(r"^(\d{8})_(\d{6})_(.+)$")
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

_PRODUCT_SUFFIXES = (
    " · Brief",
    " · Workbook",
    " Final Response Data",
    " Final Response",
    " Brief Source",
)

_PROMPT_PREFIX_RE = re.compile(
    r"^(?:please|kindly|run|execute|invoke|rebuild|build|create|generate|design|analyze|analyse|"
    r"provide|give me|help me|draft|prepare|produce|make|develop|write)\s+"
    r"(?:the\s+|a\s+|an\s+|me\s+)?",
    re.IGNORECASE,
)

_GENERIC_TITLE_TOKENS = frozenset(
    {
        "artifact",
        "brief",
        "workbook",
        "deck",
        "final",
        "response",
        "source",
        "data",
    }
)

_PROFILE_LABELS: dict[str, str] = {
    "competitive-intel": "Competitive Intel",
    "compliance-auditor": "Compliance Audit",
    "proposal-generator": "Proposal Draft",
    "price-to-win": "Price To Win",
    "oci-sweeper": "OCI Sweep",
    "ot-prototype-strategist": "OT Prototype Strategy",
    "mission-readiness-framer": "Mission Readiness Frame",
    "rfp-reverse-engineer": "RFP Reverse Engineering",
    "subcontractor-sow-builder": "Subcontractor SOW",
    "workload-analyzer": "Workload Analysis",
    "payment-terms-auditor": "Payment Terms Audit",
    "logistics-sla-auditor": "Logistics SLA Audit",
    "capital-obligations-auditor": "Capital Obligations Audit",
    "data-analyzer": "Data Analysis",
}


def humanize_run_label(run_id: str) -> str:
    """Turn a run folder id into a short human timestamp + topic slug."""
    cleaned = str(run_id or "").strip()
    match = _RUN_ID_RE.match(cleaned)
    if not match:
        return cleaned

    date_part, time_part, slug = match.groups()
    try:
        stamp = datetime.strptime(
            f"{date_part}_{time_part}",
            "%Y%m%d_%H%M%S",
        ).strftime("%d %b %H:%M")
    except ValueError:
        stamp = f"{date_part} {time_part[:2]}:{time_part[2:4]}"

    topic = " ".join(
        token
        for token in re.sub(r"[_\-]+", " ", slug).split()
        if token and not token.isdigit()
    ).strip()
    if topic:
        return f"{stamp} · {topic}"
    return stamp


def extract_markdown_h1(text: str) -> str | None:
    match = _H1_RE.search(str(text or ""))
    if not match:
        return None
    return sanitize_artifact_display_name(match.group(1).strip())


def skill_profile_labels(skill_name: str) -> set[str]:
    """Product labels that belong in the Skill column, not artifact titles."""
    labels: set[str] = set()
    profile = _PROFILE_LABELS.get(skill_name)
    if profile:
        labels.add(profile)
    labels.add(humanize_artifact_name(skill_name))
    labels.add("Huashu Design")
    return labels


def run_topic_label(run_id: str) -> str:
    """Topic slug from a run folder id, without the timestamp prefix."""
    label = humanize_run_label(run_id)
    if " · " in label:
        return label.split(" · ", 1)[1].strip()
    return ""


def strip_skill_label_from_title(title: str, skill_name: str) -> str | None:
    """Remove skill/product labels so titles stay content-first."""
    cleaned = sanitize_artifact_display_name(title) or ""
    if not cleaned:
        return None

    for label in sorted(skill_profile_labels(skill_name), key=len, reverse=True):
        cleaned = re.sub(rf"^{re.escape(label)}\s*[—–-]\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"^{re.escape(label)}\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"\s+{re.escape(label)}\s+", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"\s+{re.escape(label)}$", "", cleaned, flags=re.IGNORECASE)
        if cleaned.lower() == label.lower():
            cleaned = ""

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -—·")
    if not cleaned:
        return None

    tokens = [token for token in re.split(r"[\s·]+", cleaned.lower()) if token]
    if tokens and all(token in _GENERIC_TITLE_TOKENS for token in tokens):
        return None
    if cleaned in skill_profile_labels(skill_name):
        return None
    return cleaned


def normalize_content_title(title: str | None, skill_name: str) -> str | None:
    if not title:
        return None
    return strip_skill_label_from_title(title, skill_name)


def _workspace_root_from_run_dir(run_dir: Path) -> Path | None:
    """Resolve workspace root from ``skill_runs/<skill>/<run_id>``."""
    current = Path(run_dir).resolve()
    for _ in range(8):
        if (current / "skill_runs").is_dir():
            return current
        if current.parent == current:
            break
        current = current.parent
    return None


def _load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _mission_readiness_title(artifacts_dir: Path) -> str | None:
    brief = artifacts_dir / "brief.md"
    if brief.is_file():
        title = extract_markdown_h1(brief.read_text(encoding="utf-8", errors="replace"))
        if title:
            return normalize_content_title(title, "mission-readiness-framer")

    frame_path = artifacts_dir / "mission_readiness_frame.json"
    payload = _load_json(frame_path)
    if not isinstance(payload, dict):
        return None

    context = payload.get("opportunity_context") or {}
    opportunity = str(
        context.get("opportunity_name")
        or context.get("program_name")
        or context.get("title")
        or ""
    ).strip()
    if opportunity:
        return normalize_content_title(opportunity, "mission-readiness-framer")

    solicitation = str(
        context.get("solicitation_id")
        or context.get("contract_number")
        or context.get("piid")
        or ""
    ).strip()
    agency = str(context.get("agency") or context.get("customer") or "").strip()
    if solicitation and agency:
        return f"{agency} ({solicitation})"
    if solicitation:
        return solicitation
    if agency:
        return agency
    return None


def _competitive_intel_title(artifacts_dir: Path) -> str | None:
    for path in sorted(artifacts_dir.glob("*.json")):
        if path.name == "report.json":
            continue
        payload = _load_json(path)
        if not isinstance(payload, dict) or not payload.get("obligations"):
            continue
        try:
            from src.skills.skill_local_tools import load_skill_tool_module

            workspace_root = _workspace_root_from_run_dir(artifacts_dir.parent)
            if workspace_root is None:
                return None
            helpers = load_skill_tool_module(
                workspace_root / ".github" / "skills" / "competitive-intel",
                "competitive_intel_tools",
            )
        except Exception:
            return None
        try:
            return normalize_content_title(
                helpers.build_competitive_intel_product_title(payload),
                "competitive-intel",
            )
        except Exception:
            return None
    return None


def derive_run_content_title(skill_name: str, run_dir: Path) -> str | None:
    """Best-effort content title for every deliverable in a run."""
    artifacts_dir = Path(run_dir) / "artifacts"
    if not artifacts_dir.is_dir():
        return None

    if skill_name == "mission-readiness-framer":
        title = _mission_readiness_title(artifacts_dir)
        if title:
            return title
    elif skill_name == "competitive-intel":
        title = _competitive_intel_title(artifacts_dir)
        if title:
            return title
    elif skill_name == "huashu-design":
        from src.skills.studio_surfaces import deck_display_name, iter_studio_deliverable_paths

        for rel, path in iter_studio_deliverable_paths(artifacts_dir):
            if rel.endswith("index.html"):
                return deck_display_name(path)
        for path in sorted(artifacts_dir.glob("*.html")):
            if path.is_file():
                return humanize_artifact_name(path.name)

    for candidate in ("brief.md", "report.md", "response.md"):
        brief = artifacts_dir / candidate
        if brief.is_file():
            title = extract_markdown_h1(brief.read_text(encoding="utf-8", errors="replace"))
            if title:
                normalized = normalize_content_title(title, skill_name)
                if normalized:
                    return normalized
    return None


def read_run_invoke_prompt(run_dir: Path) -> str:
    """Return the user invoke prompt persisted on a skill run."""
    meta = read_run_metadata(run_dir)
    user_prompt = str(meta.get("user_prompt") or "").strip()
    if user_prompt:
        return user_prompt

    prompt_path = Path(run_dir) / "prompt.md"
    if not prompt_path.is_file():
        return ""

    text = prompt_path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return ""

    marker = "## User Prompt"
    if marker in text:
        tail = text.split(marker, 1)[1].strip()
        for stop in ("\n## ", "\n---"):
            if stop in tail:
                tail = tail.split(stop, 1)[0]
        return tail.strip()
    return text


def extract_prompt_variant(prompt: str, *, max_len: int = 48) -> str | None:
    """Pull a short iteration-specific phrase from the invoke prompt."""
    text = re.sub(r"\s+", " ", str(prompt or "").strip())
    if not text:
        return None

    sentence = re.split(r"[.!?\n]", text, maxsplit=1)[0].strip()
    for _ in range(3):
        trimmed = _PROMPT_PREFIX_RE.sub("", sentence).strip(" \"'")
        if trimmed == sentence:
            break
        sentence = trimmed
    sentence = sentence.strip(" \"'")
    if len(sentence) < 8:
        return None

    if len(sentence) > max_len:
        sentence = sentence[: max_len + 1].rsplit(" ", 1)[0].strip()
    return sanitize_artifact_display_name(sentence)


def strip_product_suffix(display_name: str) -> str:
    cleaned = sanitize_artifact_display_name(display_name) or ""
    for suffix in _PRODUCT_SUFFIXES:
        if cleaned.endswith(suffix):
            return cleaned[: -len(suffix)].strip()
    return cleaned


def is_weak_content_title(
    title: str,
    *,
    skill_name: str,
    run_dir: Path,
    artifact_rel: str,
) -> bool:
    """True when the title needs invoke-prompt help to distinguish iterations."""
    base = strip_product_suffix(title)
    normalized = strip_skill_label_from_title(base, skill_name)
    if not normalized:
        return True

    topic = run_topic_label(Path(run_dir).name)
    if topic and normalized.lower() == topic.lower():
        return True

    fallback = fallback_content_title(skill_name, run_dir, artifact_rel)
    if normalized.lower() == fallback.lower():
        return True

    tokens = [token for token in re.split(r"[\s·]+", normalized.lower()) if token]
    if tokens and all(token in _GENERIC_TITLE_TOKENS for token in tokens):
        return True

    if is_generic_studio_label(normalized, skill_name=skill_name, filename=artifact_rel):
        return True

    return False


def inject_prompt_variant(display_name: str, variant: str) -> str:
    """Insert a prompt-derived clause before any product suffix."""
    cleaned = sanitize_artifact_display_name(display_name) or ""
    variant_clean = sanitize_artifact_display_name(variant) or ""
    if not cleaned or not variant_clean:
        return cleaned or display_name
    if variant_clean.lower() in cleaned.lower():
        return cleaned

    for suffix in _PRODUCT_SUFFIXES:
        if cleaned.endswith(suffix):
            base = cleaned[: -len(suffix)].strip()
            return f"{base} · {variant_clean}{suffix}"
    return f"{cleaned} · {variant_clean}"


def needs_prompt_disambiguation(
    display_name: str,
    *,
    skill_name: str,
    run_dir: Path,
    artifact_rel: str,
) -> bool:
    return is_weak_content_title(
        display_name,
        skill_name=skill_name,
        run_dir=run_dir,
        artifact_rel=artifact_rel,
    )


def maybe_enrich_display_name_with_prompt(
    display_name: str,
    *,
    skill_name: str,
    run_dir: Path,
    artifact_rel: str,
    force: bool = False,
) -> str:
    """Add a prompt-derived variant when the title is weak or forced by collision."""
    if not force and not needs_prompt_disambiguation(
        display_name,
        skill_name=skill_name,
        run_dir=run_dir,
        artifact_rel=artifact_rel,
    ):
        return display_name

    variant = extract_prompt_variant(read_run_invoke_prompt(run_dir))
    if not variant:
        return display_name
    return inject_prompt_variant(display_name, variant)


def fallback_content_title(
    skill_name: str,
    run_dir: Path,
    artifact_rel: str,
) -> str:
    """Last-resort title that never repeats the skill slug or profile label."""
    topic = run_topic_label(Path(run_dir).name)
    if topic:
        return topic

    stem = Path(artifact_rel).stem or Path(artifact_rel).name
    skill_stem = skill_name.replace("-", "_")
    if stem.lower().startswith(skill_stem.lower()):
        stem = stem[len(skill_stem) :].lstrip("_-")
    if stem:
        return humanize_artifact_name(stem)
    return humanize_artifact_name(Path(artifact_rel).name)


def _generic_labels_for_skill(skill_name: str, filename: str) -> set[str]:
    profile_label = _PROFILE_LABELS.get(skill_name) or humanize_artifact_name(skill_name)
    stem = Path(filename or "artifact").name
    return {
        profile_label,
        f"{profile_label} Brief",
        f"{profile_label} Workbook",
        f"{profile_label} Final Response",
        f"{profile_label} Final Response Data",
        humanize_artifact_name(stem),
        "Huashu Design Brief",
        stem,
    }


def is_generic_studio_label(
    display_name: str,
    *,
    skill_name: str,
    filename: str,
) -> bool:
    cleaned = sanitize_artifact_display_name(display_name) or ""
    if not cleaned:
        return True
    return cleaned in _generic_labels_for_skill(skill_name, filename)


def format_product_display_name(
    content_title: str,
    *,
    filename: str,
    ext: str = "",
) -> str:
    """Attach a product hint only when the content title does not already say it."""
    title = sanitize_artifact_display_name(content_title) or humanize_artifact_name(filename)
    lower = title.lower()
    leaf = Path(filename or "").name.lower()
    extension = (ext or Path(filename or "").suffix.lstrip(".")).lower()

    if extension == "xlsx" or "workbook" in leaf:
        if "workbook" in lower:
            return title
        if "brief" in lower:
            return re.sub(r"\bbrief\b", "Workbook", title, count=1, flags=re.IGNORECASE)
        return f"{title} · Workbook"

    if extension == "docx" or "brief" in leaf:
        if "brief" in lower or "workbook" in lower:
            return title
        return f"{title} · Brief"

    if leaf.endswith("index.html") or "deck" in leaf:
        return title

    return title


def resolve_studio_display_name(
    *,
    skill_name: str,
    run_dir: Path,
    artifact_rel: str,
    manifest_entry: dict[str, Any] | None,
    content_title: str | None = None,
) -> str:
    """Resolve a user-facing deliverable title without repeating the skill slug."""
    manifest_name = sanitize_artifact_display_name(
        (manifest_entry or {}).get("display_name")
    )
    if manifest_name and not is_generic_studio_label(
        manifest_name,
        skill_name=skill_name,
        filename=artifact_rel,
    ):
        stripped = strip_skill_label_from_title(manifest_name, skill_name)
        if stripped:
            return stripped

    base_title = content_title or derive_run_content_title(skill_name, run_dir)
    if not base_title:
        base_title = fallback_content_title(skill_name, run_dir, artifact_rel)

    ext = Path(artifact_rel).suffix.lstrip(".").lower()
    resolved = format_product_display_name(
        base_title,
        filename=artifact_rel,
        ext=ext,
    )
    return strip_skill_label_from_title(resolved, skill_name) or resolved


__all__ = [
    "derive_run_content_title",
    "extract_markdown_h1",
    "extract_prompt_variant",
    "fallback_content_title",
    "format_product_display_name",
    "humanize_run_label",
    "inject_prompt_variant",
    "is_generic_studio_label",
    "is_weak_content_title",
    "maybe_enrich_display_name_with_prompt",
    "needs_prompt_disambiguation",
    "normalize_content_title",
    "read_run_invoke_prompt",
    "resolve_studio_display_name",
    "run_topic_label",
    "skill_profile_labels",
    "strip_product_suffix",
    "strip_skill_label_from_title",
]