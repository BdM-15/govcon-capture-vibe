"""Deterministic helpers for mission-readiness-framer Studio deliverables."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_URL_RE = re.compile(r"https?://[^\s\)>\"']+", re.IGNORECASE)

_MINIMUM_COUNTS: dict[str, int] = {
    "customer_pain_points": 4,
    "current_methods": 3,
    "innovation_opportunities": 3,
    "importance_signals": 4,
    "implicit_criteria": 3,
    "win_theme_candidates": 3,
    "verbatim_extracts": 6,
    "eval_crosswalk": 4,
    "clarification_questions": 3,
}

_MIN_BRIEF_LINES = 120
_MIN_OVERLAY_BRIEF_LINES = 30
_MIN_CROSSWALK_READINESS_CHARS = 40


def _join_list(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, (str, int, float, bool)):
                parts.append(str(item))
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        return ", ".join(parts)
    return str(value)


def detect_capability_overlay_request(user_prompt: str) -> dict[str, Any] | None:
    """Return overlay hints when the user names an external vendor/platform/URL."""
    text = str(user_prompt or "").strip()
    if not text:
        return None

    urls = [url.rstrip(".,;") for url in _URL_RE.findall(text)]
    if not urls:
        return None

    vendor = ""
    company_match = re.search(
        r"(?:company|vendor|platform|partner|firm)\s+([A-Z][A-Za-z0-9&.,'\- ]{2,60}?)(?:\s+with|\s+and|\s+using|[,.]|$)",
        text,
        re.IGNORECASE,
    )
    if company_match:
        vendor = company_match.group(1).strip(" .,")
    if not vendor:
        named = re.search(
            r"\b([A-Z][A-Za-z0-9&.'\-]+(?:,\s*Inc\.?| LLC| Corp\.?| Platform))\b",
            text,
        )
        if named:
            vendor = named.group(1).strip()

    return {
        "requested": True,
        "vendor": vendor,
        "urls": urls,
    }


def _section_line_count(markdown: str, heading: str) -> int:
    lines = str(markdown or "").splitlines()
    start = -1
    for index, line in enumerate(lines):
        if line.strip().lower() == heading.strip().lower():
            start = index + 1
            break
    if start < 0:
        return 0
    count = 0
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.strip():
            count += 1
    return count


def _thin_crosswalk_rows(rows: list[Any]) -> list[str]:
    issues: list[str] = []
    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            issues.append(f"eval_crosswalk row {index} is not an object")
            continue
        factor = str(raw.get("evaluation_factor") or "").strip()
        clusters = raw.get("pws_clusters") or []
        readiness = str(raw.get("readiness_link") or "").strip()
        proof = str(raw.get("proof_expected") or "").strip()
        if not factor:
            issues.append(f"eval_crosswalk row {index} missing evaluation_factor")
        if not isinstance(clusters, list) or not clusters:
            issues.append(f"eval_crosswalk row {index} missing pws_clusters")
        if len(readiness) < _MIN_CROSSWALK_READINESS_CHARS:
            issues.append(
                f"eval_crosswalk row {index} readiness_link too thin "
                f"({len(readiness)} chars; need {_MIN_CROSSWALK_READINESS_CHARS}+)"
            )
        if len(proof) < 20:
            issues.append(f"eval_crosswalk row {index} proof_expected too thin")
    return issues


def validate_mission_readiness_run(
    run_dir: Path,
    *,
    user_prompt: str = "",
) -> list[str]:
    """Post-run depth audit for mission-readiness-framer artifacts."""
    issues: list[str] = []
    overlay_request = detect_capability_overlay_request(user_prompt)
    artifacts_dir = Path(run_dir) / "artifacts"
    frame_path = artifacts_dir / "mission_readiness_frame.json"
    brief_path = artifacts_dir / "brief.md"

    payload: dict[str, Any] | None = None
    if frame_path.is_file():
        try:
            loaded = json.loads(frame_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, json.JSONDecodeError):
            issues.append("mission_readiness_frame.json is unreadable")
    else:
        issues.append("missing mission_readiness_frame.json")

    brief_text = ""
    if brief_path.is_file():
        try:
            brief_text = brief_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            issues.append("brief.md is unreadable")
    else:
        issues.append("missing brief.md")

    if brief_text:
        line_count = len([line for line in brief_text.splitlines() if line.strip()])
        if line_count < _MIN_BRIEF_LINES:
            issues.append(
                f"brief.md too short ({line_count} non-empty lines; minimum {_MIN_BRIEF_LINES})"
            )
        if "## Eval cross-walk" not in brief_text and "## Eval Cross-walk" not in brief_text:
            issues.append("brief.md missing Eval cross-walk section")

    if payload:
        for key, minimum in _MINIMUM_COUNTS.items():
            rows = payload.get(key)
            if not isinstance(rows, list):
                issues.append(f"missing or invalid array: {key}")
                continue
            if len(rows) < minimum:
                issues.append(f"{key} has {len(rows)} entries (minimum {minimum})")

        crosswalk = payload.get("eval_crosswalk")
        if isinstance(crosswalk, list):
            issues.extend(_thin_crosswalk_rows(crosswalk))
            factors = {
                str(row.get("evaluation_factor") or "").strip().lower()
                for row in crosswalk
                if isinstance(row, dict) and str(row.get("evaluation_factor") or "").strip()
            }
            if len(factors) < len(crosswalk):
                issues.append("eval_crosswalk contains duplicate evaluation_factor labels")

        overlay = payload.get("capability_overlay")
        if overlay_request:
            if not isinstance(overlay, dict):
                issues.append(
                    "user requested external capability overlay but capability_overlay is missing"
                )
            else:
                mappings = overlay.get("pain_point_mappings") or overlay.get("mappings") or []
                innovations = overlay.get("innovation_links") or []
                capabilities = overlay.get("platform_capabilities") or []
                if not str(overlay.get("vendor") or "").strip():
                    issues.append("capability_overlay.vendor is empty")
                if len(capabilities) < 3:
                    issues.append(
                        "capability_overlay.platform_capabilities has fewer than 3 entries"
                    )
                if len(mappings) < 2:
                    issues.append(
                        "capability_overlay needs at least 2 pain_point_mappings"
                    )
                if len(innovations) < 2:
                    issues.append(
                        "capability_overlay needs at least 2 innovation_links"
                    )

            overlay_lines = _section_line_count(brief_text, "## Capability overlay (user-directed)")
            if overlay_lines < _MIN_OVERLAY_BRIEF_LINES:
                issues.append(
                    "brief.md Capability overlay section too thin "
                    f"({overlay_lines} lines; minimum {_MIN_OVERLAY_BRIEF_LINES} when user requests vendor/platform review)"
                )

    transcript_path = Path(run_dir) / "transcript.json"
    if transcript_path.is_file():
        try:
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            if isinstance(transcript, list):
                kg_calls = sum(
                    1
                    for entry in transcript
                    if isinstance(entry, dict)
                    and entry.get("kind") == "tool"
                    and entry.get("name") == "kg_chunks"
                )
                if kg_calls < 5:
                    issues.append(f"only {kg_calls} kg_chunks calls (minimum 5)")
                web_calls = sum(
                    1
                    for entry in transcript
                    if isinstance(entry, dict)
                    and entry.get("kind") == "tool"
                    and str(entry.get("name") or "").startswith("web_")
                )
                if overlay_request and web_calls < 1:
                    issues.append(
                        "user requested external capability review but no web_fetch/web_research calls"
                    )
        except (OSError, json.JSONDecodeError):
            pass

    finish_path = Path(run_dir) / "run.md"
    if finish_path.is_file():
        envelope = finish_path.read_text(encoding="utf-8", errors="replace")
        if "finish_reason: max_turns" in envelope or "forced_summary" in envelope:
            issues.append("run hit max_turns forced summary — output likely truncated")

    return issues


def write_depth_audit(run_dir: Path, issues: list[str]) -> Path:
    """Persist post-run depth audit beside artifacts."""
    out = Path(run_dir) / "artifacts" / "depth_audit.json"
    payload = {
        "ok": not issues,
        "issue_count": len(issues),
        "issues": issues,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def build_workbook_payload(envelope: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Flatten the skill envelope into workbook-friendly top-level arrays."""
    if not isinstance(envelope, dict):
        return {"frame_summary": []}

    frame = envelope.get("mission_readiness_frame") or {}
    context = envelope.get("opportunity_context") or {}

    frame_summary = [
        {
            "solicitation_id": context.get("solicitation_id"),
            "agency": context.get("agency"),
            "readiness_outcome": frame.get("readiness_outcome"),
            "confidence": frame.get("confidence"),
            "our_read": frame.get("our_read"),
            "failure_modes_feared": _join_list(frame.get("failure_modes_feared")),
            "source_chunk_ids": _join_list(frame.get("source_chunk_ids")),
        }
    ]

    return {
        "frame_summary": frame_summary,
        "workload_enablers": list(frame.get("workload_enablers") or []),
        "readiness_signals": list(frame.get("readiness_signals") or []),
        "customer_pain_points": list(envelope.get("customer_pain_points") or []),
        "importance_signals": list(envelope.get("importance_signals") or []),
        "implicit_criteria": list(envelope.get("implicit_criteria") or []),
        "win_theme_candidates": list(envelope.get("win_theme_candidates") or []),
        "current_methods": list(envelope.get("current_methods") or []),
        "innovation_opportunities": list(envelope.get("innovation_opportunities") or []),
        "verbatim_extracts": list(envelope.get("verbatim_extracts") or []),
        "eval_crosswalk": list(envelope.get("eval_crosswalk") or []),
        "clarification_questions": list(envelope.get("clarification_questions") or []),
        "claim_gaps": [
            {"gap": gap}
            for gap in (envelope.get("claim_gaps") or [])
            if str(gap).strip()
        ],
        "capability_overlay": list(
            [envelope.get("capability_overlay")]
            if isinstance(envelope.get("capability_overlay"), dict)
            else []
        ),
    }


def write_workbook_source(artifacts_dir: Path, envelope: dict[str, Any]) -> Path | None:
    """Write mission_readiness_workbook.json for render_xlsx when frame JSON exists."""
    source = artifacts_dir / "mission_readiness_frame.json"
    if not source.is_file():
        return None
    payload = envelope if envelope else json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    out = artifacts_dir / "mission_readiness_workbook.json"
    out.write_text(
        json.dumps(build_workbook_payload(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out