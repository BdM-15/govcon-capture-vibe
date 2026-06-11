"""Human-readable Studio labels derived from run content, not skill slugs."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from src.skills.run_metadata import humanize_artifact_name, sanitize_artifact_display_name

_RUN_ID_RE = re.compile(r"^(\d{8})_(\d{6})_(.+)$")
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

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
            return title

    frame_path = artifacts_dir / "mission_readiness_frame.json"
    payload = _load_json(frame_path)
    if not isinstance(payload, dict):
        return None

    context = payload.get("opportunity_context") or {}
    solicitation = str(
        context.get("solicitation_id")
        or context.get("contract_number")
        or context.get("piid")
        or ""
    ).strip()
    agency = str(context.get("agency") or context.get("customer") or "").strip()
    if solicitation and agency:
        return f"Mission Readiness Frame — {agency} ({solicitation})"
    if solicitation:
        return f"Mission Readiness Frame — {solicitation}"
    if agency:
        return f"Mission Readiness Frame — {agency}"
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

            helpers = load_skill_tool_module(
                artifacts_dir.parent.parent.parent / ".github" / "skills" / "competitive-intel",
                "competitive_intel_tools",
            )
        except Exception:
            return None
        try:
            return helpers.build_competitive_intel_product_title(payload)
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

    for candidate in ("brief.md", "report.md"):
        brief = artifacts_dir / candidate
        if brief.is_file():
            title = extract_markdown_h1(brief.read_text(encoding="utf-8", errors="replace"))
            if title:
                return title
    return None


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
        return manifest_name

    base_title = content_title or derive_run_content_title(skill_name, run_dir)
    if not base_title:
        profile = _PROFILE_LABELS.get(skill_name)
        base_title = profile or humanize_artifact_name(Path(artifact_rel).name)

    ext = Path(artifact_rel).suffix.lstrip(".").lower()
    return format_product_display_name(
        base_title,
        filename=artifact_rel,
        ext=ext,
    )


__all__ = [
    "derive_run_content_title",
    "extract_markdown_h1",
    "format_product_display_name",
    "humanize_run_label",
    "is_generic_studio_label",
    "resolve_studio_display_name",
]