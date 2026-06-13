"""Deterministic helpers for mission-readiness-framer Studio deliverables."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_URL_RE = re.compile(r"https?://[^\s\)>\"']+", re.IGNORECASE)

_REQUIRED_ARRAY_KEYS = (
    "customer_pain_points",
    "current_methods",
    "innovation_opportunities",
    "importance_signals",
    "implicit_criteria",
    "win_theme_candidates",
    "verbatim_extracts",
    "eval_crosswalk",
    "clarification_questions",
)

_PLACEHOLDER_RE = re.compile(
    r"^(tbd|todo|n/?a|none|placeholder|too short|\.{3,})$",
    re.IGNORECASE,
)

_EVAL_CROSSWALK_HEADING_RE = re.compile(
    r"^##\s*(?:\d+\.\s*)?eval(?:uation)?\s+cross[- ]?walk\b",
    re.IGNORECASE,
)

_DELIVERABLE_FILENAMES = frozenset(
    {"mission_readiness_frame.json", "brief.md"},
)

# Aligns with platform retrieval plan surface count (package + mission-connection inquiries).
_MIN_KG_CHUNKS_PASSES = 12
_MIN_KG_ENTITIES_PASSES = 1
_EVAL_ENTITY_TYPES = frozenset({"evaluation_factor", "subfactor"})

# KG often returns process/meta labels alongside Section M factors — not crosswalk rows.
_NON_MATERIAL_EVAL_RE = re.compile(
    r"(?:"
    r"\(general\)|methodology|decision document|competitive range|assessment reporting|"
    r"evaluation strengths|quality evaluation|relevancy assessment|confidence assessment|"
    r"tradeoff analysis|rating scale|adjectival|source selection decision|"
    r"contractor performance assessment reporting|past performance quality evaluation"
    r")",
    re.IGNORECASE,
)

_MIN_SCRATCHPAD_FOR_QUAL_DEPTH = 150_000


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


def _load_transcript(run_dir: Path) -> list[dict[str, Any]]:
    transcript_path = Path(run_dir) / "transcript.json"
    if not transcript_path.is_file():
        return []
    try:
        loaded = json.loads(transcript_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return loaded if isinstance(loaded, list) else []


def _read_user_prompt(run_dir: Path, *, fallback: str = "") -> str:
    run_md = Path(run_dir) / "run.md"
    if run_md.is_file():
        text = run_md.read_text(encoding="utf-8", errors="replace")
        marker = "## User Prompt\n\n"
        if marker in text:
            tail = text.split(marker, 1)[1]
            return tail.split("\n## ", 1)[0].strip()
    return fallback


def _transcript_tool_stats(transcript: list[dict[str, Any]]) -> dict[str, Any]:
    kg_chunks_calls = 0
    kg_entities_calls = 0
    web_calls = 0
    chunks_retrieved = 0
    eval_entities_retrieved = 0
    eval_types_requested = False
    eval_entities_peak = 0

    for entry in transcript:
        if not isinstance(entry, dict) or entry.get("kind") != "tool":
            continue
        name = str(entry.get("name") or "")
        if name == "kg_chunks":
            kg_chunks_calls += 1
            extra = entry.get("extra") or {}
            if isinstance(extra, dict):
                chunks_retrieved += int(extra.get("chunk_count") or 0)
        elif name == "kg_entities":
            kg_entities_calls += 1
            args_raw = entry.get("arguments") or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else {}
            except json.JSONDecodeError:
                args = {}
            types = args.get("types") if isinstance(args, dict) else None
            if isinstance(types, list):
                normalized = {str(value).strip().lower() for value in types if value}
                if normalized & _EVAL_ENTITY_TYPES:
                    eval_types_requested = True
            extra = entry.get("extra") or {}
            if isinstance(extra, dict):
                counts = extra.get("entity_counts_by_type") or {}
                if isinstance(counts, dict):
                    call_eval = 0
                    for key, count in counts.items():
                        if str(key).strip().lower() in _EVAL_ENTITY_TYPES:
                            call_eval += int(count or 0)
                    if call_eval > 0:
                        eval_entities_peak = max(eval_entities_peak, call_eval)
        elif name.startswith("web_"):
            web_calls += 1

    return {
        "kg_chunks_calls": kg_chunks_calls,
        "kg_entities_calls": kg_entities_calls,
        "web_calls": web_calls,
        "chunks_retrieved": chunks_retrieved,
        "eval_entities_retrieved": eval_entities_peak,
        "eval_types_requested": eval_types_requested,
    }


def _has_eval_crosswalk_section(markdown: str) -> bool:
    for line in str(markdown or "").splitlines():
        if _EVAL_CROSSWALK_HEADING_RE.match(line.strip()):
            return True
    return False


def _harness_retrieval_complete(run_dir: Path) -> bool:
    try:
        from src.skills.research_harness import load_harness_state
        from src.skills.research_plan import auto_saturate_stalled_surfaces, retrieval_plan_complete
    except ImportError:
        return False
    state = load_harness_state(run_dir)
    if not state:
        return False
    auto_saturate_stalled_surfaces(state)
    return retrieval_plan_complete(state)


def _is_compiler_run(run_dir: Path | None) -> bool:
    if run_dir is None:
        return False
    try:
        from src.skills.mission_readiness_merge import is_compiler_run_dir

        return is_compiler_run_dir(run_dir)
    except ImportError:
        return False


def _retrieval_phase_issues(
    transcript: list[dict[str, Any]],
    *,
    overlay_request: dict[str, Any] | None,
    run_dir: Path | None = None,
) -> list[str]:
    if run_dir is not None and _is_compiler_run(run_dir):
        stats = _transcript_tool_stats(transcript)
        issues: list[str] = []
        if overlay_request and stats["web_calls"] < 1:
            issues.append(
                "retrieval incomplete: user requested external capability overlay — "
                "call web_fetch/web_research before writing deliverables"
            )
        return issues
    if run_dir is not None and _harness_retrieval_complete(run_dir):
        stats = _transcript_tool_stats(transcript)
        issues: list[str] = []
        if overlay_request and stats["web_calls"] < 1:
            issues.append(
                "retrieval incomplete: user requested external capability overlay — "
                "call web_fetch/web_research before writing deliverables"
            )
        return issues
    stats = _transcript_tool_stats(transcript)
    issues: list[str] = []
    if stats["kg_entities_calls"] < _MIN_KG_ENTITIES_PASSES:
        issues.append(
            "retrieval incomplete: run kg_entities on the full-package type slice "
            "(include evaluation_factor and subfactor) before writing deliverables"
        )
    elif not stats["eval_types_requested"]:
        issues.append(
            "retrieval incomplete: kg_entities must request evaluation_factor and subfactor types"
        )
    if stats["kg_chunks_calls"] < _MIN_KG_CHUNKS_PASSES:
        issues.append(
            "retrieval incomplete: complete the retrieval plan — package mechanics, "
            "mission-connection inquiries, and Shipley passes (pains, needs/wants, win themes) "
            f"(have {stats['kg_chunks_calls']}, plan expects {_MIN_KG_CHUNKS_PASSES} "
            "purposeful kg_chunks calls)"
        )
    if overlay_request and stats["web_calls"] < 1:
        issues.append(
            "retrieval incomplete: user requested external capability overlay — "
            "call web_fetch/web_research before writing deliverables"
        )
    return issues


def _is_material_eval_factor(label: Any) -> bool:
    text = str(label or "").strip()
    if not text or text.lower().startswith("entity:"):
        return False
    return not _NON_MATERIAL_EVAL_RE.search(text)


def _material_crosswalk_rows(crosswalk: list[Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in crosswalk
        if isinstance(row, dict)
        and _is_material_eval_factor(row.get("evaluation_factor"))
    ]


def _expected_material_crosswalk_rows(
    eval_entities_retrieved: int,
    run_dir: Path | None,
) -> int:
    if eval_entities_retrieved <= 3:
        return eval_entities_retrieved
    scratchpad_chars = 0
    if run_dir is not None:
        try:
            from src.skills.research_harness import load_harness_state
        except ImportError:
            load_harness_state = None  # type: ignore[assignment,misc]
        if load_harness_state is not None:
            state = load_harness_state(run_dir)
            if state:
                scratchpad_chars = int(state.get("scratchpad_chars") or 0)
    if scratchpad_chars < _MIN_SCRATCHPAD_FOR_QUAL_DEPTH:
        return eval_entities_retrieved
    # Section M spine: factors + subfactors — not every KG descriptor label.
    return max(12, min(eval_entities_retrieved, 22))


def _eval_crosswalk_quality_issues(crosswalk: list[Any]) -> list[str]:
    issues: list[str] = []
    material_rows = _material_crosswalk_rows(crosswalk)
    total = sum(
        1
        for row in crosswalk
        if isinstance(row, dict) and str(row.get("evaluation_factor") or "").strip()
    )
    if total >= 10 and len(material_rows) < max(8, int(total * 0.65)):
        issues.append(
            "eval_crosswalk contains non-material/meta KG labels padded as rows — "
            "keep Section M factors/subfactors only"
        )
    primary_chunks: list[str] = []
    for row in material_rows:
        chunk_ids = row.get("source_chunk_ids") or []
        if isinstance(chunk_ids, list) and chunk_ids:
            primary_chunks.append(str(chunk_ids[0]))
    if len(primary_chunks) >= 8:
        counts: dict[str, int] = {}
        for chunk_id in primary_chunks:
            counts[chunk_id] = counts.get(chunk_id, 0) + 1
        top_chunk, top_count = max(counts.items(), key=lambda item: item[1])
        if top_count / len(primary_chunks) > 0.45:
            issues.append(
                "eval_crosswalk over-relies on one source chunk "
                f"({top_chunk} in {top_count}/{len(primary_chunks)} material rows) — "
                "diversify citations from scratchpad"
            )
    return issues


def _brief_narrative_depth_issues(brief_text: str, run_dir: Path | None) -> list[str]:
    if run_dir is None:
        return []
    if _is_compiler_run(run_dir):
        return []
    try:
        from src.skills.research_harness import load_harness_state
    except ImportError:
        return []
    state = load_harness_state(run_dir)
    if not state or int(state.get("scratchpad_chars") or 0) < _MIN_SCRATCHPAD_FOR_QUAL_DEPTH:
        return []
    text = str(brief_text or "").strip()
    if not text:
        return ["brief.md is empty — synthesis must produce a research-depth narrative"]
    issues: list[str] = []
    char_count = len(text)
    line_count = len(text.splitlines())
    if char_count < 12_000:
        issues.append(
            f"brief.md is only {char_count} chars — need >=12000 (~8+ pages) of analytical "
            "capture narrative after full-package retrieval"
        )
    if line_count < 100:
        issues.append(
            f"brief.md is only {line_count} lines — expand each major section with "
            "multi-paragraph reasoning over scratchpad evidence"
        )
    bullet_like = 0
    prose_lines = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|"):
            continue
        if stripped.startswith(("- ", "* ", "1.", "2.", "3.")) or stripped.startswith("##"):
            bullet_like += 1
        elif len(stripped) > 80:
            prose_lines += 1
    if bullet_like > prose_lines * 2 and prose_lines < 25:
        issues.append(
            "brief.md is mostly bullets/tables — add multi-paragraph analytical prose "
            "with Our read / Likely / Signal judgments per section"
        )
    return issues


def _qualitative_depth_issues(
    payload: dict[str, Any],
    run_dir: Path | None,
) -> list[str]:
    if run_dir is None:
        return []
    if _is_compiler_run(run_dir):
        return []
    try:
        from src.skills.research_harness import load_harness_state
    except ImportError:
        return []
    state = load_harness_state(run_dir)
    if not state or int(state.get("scratchpad_chars") or 0) < _MIN_SCRATCHPAD_FOR_QUAL_DEPTH:
        return []
    issues: list[str] = []
    minimums = {
        "customer_pain_points": 5,
        "verbatim_extracts": 5,
        "win_theme_candidates": 3,
        "importance_signals": 3,
        "implicit_criteria": 2,
        "current_methods": 3,
        "innovation_opportunities": 3,
    }
    for key, minimum in minimums.items():
        rows = payload.get(key)
        count = len(rows) if isinstance(rows, list) else 0
        if count < minimum:
            issues.append(
                f"{key} has {count} entries (need >= {minimum} after full-package retrieval) — "
                "expand from scratchpad evidence"
            )
    return issues


def _solicitation_coverage_issues(
    payload: dict[str, Any] | None,
    *,
    eval_entities_retrieved: int,
    run_dir: Path | None = None,
) -> list[str]:
    if run_dir is not None and _is_compiler_run(run_dir):
        if not payload:
            return []
        crosswalk = payload.get("eval_crosswalk")
        if not isinstance(crosswalk, list) or not crosswalk:
            return [
                "eval_crosswalk is empty after handoff merge — compiler must preserve "
                "upstream eval rows or document gaps in claim_gaps[]"
            ]
        return _eval_crosswalk_quality_issues(crosswalk)
    if not payload or eval_entities_retrieved <= 0:
        return []
    crosswalk = payload.get("eval_crosswalk")
    if not isinstance(crosswalk, list):
        return []
    material_rows = _material_crosswalk_rows(crosswalk)
    expected = _expected_material_crosswalk_rows(eval_entities_retrieved, run_dir)
    issues: list[str] = []
    if len(material_rows) < expected:
        issues.append(
            "eval_crosswalk under-covers material Section M factors/subfactors "
            f"({len(material_rows)} material rows vs ~{expected} expected) — "
            "add substantive rows or document gaps in claim_gaps[]"
        )
    issues.extend(_eval_crosswalk_quality_issues(crosswalk))
    return issues


def _continuation_message(issues: list[str], *, compiler: bool = False) -> str:
    joined = "; ".join(issues)
    if compiler:
        return (
            "Compiler run incomplete — do NOT finalize yet. "
            f"{joined}. "
            "Expand artifacts/brief.md from merged mission_readiness_frame.json and "
            "research_scratchpad.md — do not re-run kg_chunks/kg_entities. "
            "Preserve the eval cross-walk table rows; mirror claim_gaps[] in section 8."
        )
    return (
        "Run incomplete — do NOT finalize yet. "
        f"{joined}. "
        "Continue agentic retrieval: call kg_entities for evaluation_factor and subfactor, "
        "run additional kg_chunks until every material factor/subfactor and package surface "
        "is covered, expand mission_readiness_frame.json and brief.md with substantive "
        "evidence-backed content, then stop only when coverage is complete or gaps are in "
        "claim_gaps[]. Your final assistant message must copy brief.md verbatim."
    )


def artifact_continue_message(run_dir: Path) -> str | None:
    """Return a continuation nudge when retrieval or deliverables are still incomplete."""
    run_path = Path(run_dir)
    user_prompt = _read_user_prompt(run_path)
    overlay_request = detect_capability_overlay_request(user_prompt)
    transcript = _load_transcript(run_path)
    issues: list[str] = []

    issues.extend(
        _retrieval_phase_issues(
            transcript,
            overlay_request=overlay_request,
            run_dir=run_path,
        )
    )

    artifacts_dir = run_path / "artifacts"
    frame_path = artifacts_dir / "mission_readiness_frame.json"
    brief_path = artifacts_dir / "brief.md"
    payload: dict[str, Any] | None = None
    brief_text = ""

    if not frame_path.is_file():
        issues.append("missing artifacts/mission_readiness_frame.json")
    else:
        try:
            loaded = json.loads(frame_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
            else:
                issues.append("artifacts/mission_readiness_frame.json (invalid JSON)")
        except (OSError, json.JSONDecodeError):
            issues.append("artifacts/mission_readiness_frame.json (unreadable)")

    if not brief_path.is_file():
        issues.append("missing artifacts/brief.md")
    else:
        try:
            brief_text = brief_path.read_text(encoding="utf-8", errors="replace").strip()
            if not brief_text:
                issues.append("artifacts/brief.md (empty)")
        except OSError:
            issues.append("artifacts/brief.md (unreadable)")

    if brief_text and not _has_eval_crosswalk_section(brief_text):
        issues.append("brief.md missing Eval cross-walk section")

    stats = _transcript_tool_stats(transcript)
    issues.extend(
        _solicitation_coverage_issues(
            payload,
            eval_entities_retrieved=int(stats["eval_entities_retrieved"]),
            run_dir=run_path,
        )
    )
    if payload is not None:
        issues.extend(_qualitative_depth_issues(payload, run_path))

    if payload is not None and brief_text:
        depth_issues = validate_mission_readiness_run(
            run_path,
            user_prompt=user_prompt,
        )
        issues.extend(depth_issues)

    deduped: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        if issue not in seen:
            seen.add(issue)
            deduped.append(issue)
    if not deduped:
        return None
    return _continuation_message(deduped, compiler=_is_compiler_run(run_path))


def validate_write_file(
    run_dir: Path,
    *,
    path: str,
    content: str,
    user_prompt: str = "",
) -> str | None:
    """Block deliverable writes until multi-pass package retrieval has run."""
    cleaned = str(path or "").replace("\\", "/").split("/")[-1].lower()
    if cleaned not in _DELIVERABLE_FILENAMES:
        return None

    prompt = user_prompt.strip() or _read_user_prompt(Path(run_dir))
    overlay_request = detect_capability_overlay_request(prompt)
    transcript = _load_transcript(Path(run_dir))
    issues = _retrieval_phase_issues(
        transcript,
        overlay_request=overlay_request,
        run_dir=Path(run_dir),
    )
    if issues:
        return (
            f"write_file blocked for {cleaned}: {issues[0]} "
            "Complete the next step in retrieval_plan.json before drafting."
        )

    if _is_compiler_run(Path(run_dir)) and cleaned == "mission_readiness_frame.json":
        return (
            "write_file blocked for mission_readiness_frame.json: compiler mode — "
            "frame is locked after deterministic handoff merge"
        )

    if cleaned == "mission_readiness_frame.json":
        try:
            loaded = json.loads(content)
        except json.JSONDecodeError:
            return None
        if isinstance(loaded, dict):
            helpers = _content_gate_helpers()
            if helpers is not None:
                frame_fn = helpers[2]
                for issue in frame_fn(loaded):
                    return f"write_file blocked for {cleaned}: {issue}"
    return None


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


def _section_content_lines(markdown: str, heading: str) -> list[str]:
    lines = str(markdown or "").splitlines()
    start = -1
    for index, line in enumerate(lines):
        if line.strip().lower() == heading.strip().lower():
            start = index + 1
            break
    if start < 0:
        return []
    content: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        stripped = line.strip()
        if stripped:
            content.append(stripped)
    return content


def _is_placeholder_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    return bool(_PLACEHOLDER_RE.match(text))


def _content_gate_helpers():
    try:
        from src.skills.readiness_content_gates import (
            acronym_issues_for_readiness_output,
            acronym_issues_for_text,
            substance_issues_for_crosswalk,
            substance_issues_for_frame_and_brief,
            substance_issues_for_frame_payload,
        )
    except ImportError:
        return None
    return (
        acronym_issues_for_readiness_output,
        substance_issues_for_crosswalk,
        substance_issues_for_frame_payload,
        substance_issues_for_frame_and_brief,
    )


def _thin_crosswalk_rows(rows: list[Any]) -> list[str]:
    issues: list[str] = []
    helpers = _content_gate_helpers()
    substance_fn = helpers[1] if helpers else None
    if substance_fn is not None:
        issues.extend(substance_fn(rows))
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
        if _is_placeholder_text(readiness):
            issues.append(f"eval_crosswalk row {index} readiness_link missing or placeholder")
        if _is_placeholder_text(proof):
            issues.append(f"eval_crosswalk row {index} proof_expected missing or placeholder")
    return issues


def _readiness_content_issues(
    payload: dict[str, Any] | None,
    brief_text: str,
    *,
    run_dir: Path | None = None,
) -> list[str]:
    helpers = _content_gate_helpers()
    if helpers is None:
        return []
    acronym_fn, _, frame_fn, frame_brief_fn = helpers
    issues: list[str] = []
    if payload is not None:
        issues.extend(frame_fn(payload))
    compiler_mode = run_dir is not None and _is_compiler_run(run_dir)
    issues.extend(
        frame_brief_fn(
            payload,
            brief_text,
            skip_tail_compression=compiler_mode,
        )
    )
    issues.extend(
        acronym_fn(
            brief_text=brief_text,
            payload=payload,
            label="readiness output",
        )
    )
    return issues


def _overlay_content_issues(overlay: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not str(overlay.get("vendor") or "").strip():
        issues.append("capability_overlay.vendor is empty")

    capabilities = overlay.get("platform_capabilities") or []
    mappings = overlay.get("pain_point_mappings") or overlay.get("mappings") or []
    innovations = overlay.get("innovation_links") or []

    if not isinstance(capabilities, list) or not capabilities:
        issues.append("capability_overlay.platform_capabilities is missing or empty")
    if not isinstance(mappings, list) or not mappings:
        issues.append("capability_overlay.pain_point_mappings is missing or empty")
    if not isinstance(innovations, list) or not innovations:
        issues.append("capability_overlay.innovation_links is missing or empty")
    return issues


def validate_skill_run(
    run_dir: Path,
    *,
    user_prompt: str = "",
) -> list[str]:
    """Platform hook — post-run qualitative audit for this skill."""
    return validate_mission_readiness_run(run_dir, user_prompt=user_prompt)


def validate_mission_readiness_run(
    run_dir: Path,
    *,
    user_prompt: str = "",
) -> list[str]:
    """Post-run qualitative audit for mission-readiness-framer artifacts."""
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
        if not _has_eval_crosswalk_section(brief_text):
            issues.append("brief.md missing Eval cross-walk section")
        if not [line for line in brief_text.splitlines() if line.strip()]:
            issues.append("brief.md is empty")
        issues.extend(_brief_narrative_depth_issues(brief_text, Path(run_dir)))

    issues.extend(_readiness_content_issues(payload, brief_text, run_dir=Path(run_dir)))

    if payload:
        for key in _REQUIRED_ARRAY_KEYS:
            rows = payload.get(key)
            if not isinstance(rows, list):
                if (
                    _is_compiler_run(Path(run_dir))
                    and key in {"verbatim_extracts", "clarification_questions"}
                ):
                    continue
                issues.append(f"missing or invalid array: {key}")
            elif _is_compiler_run(Path(run_dir)) and key in {
                "verbatim_extracts",
                "clarification_questions",
            } and not rows:
                continue

        crosswalk = payload.get("eval_crosswalk")
        if isinstance(crosswalk, list):
            if not crosswalk:
                issues.append("eval_crosswalk is empty — cross-walk every material factor from the package or log claim_gaps[]")
            else:
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
                issues.extend(_overlay_content_issues(overlay))

            overlay_lines = _section_content_lines(
                brief_text,
                "## Capability overlay (user-directed)",
            )
            if not overlay_lines:
                issues.append(
                    "brief.md missing substantive Capability overlay section when user requests vendor/platform review"
                )

    transcript = _load_transcript(Path(run_dir))
    if transcript:
        stats = _transcript_tool_stats(transcript)
        issues.extend(
            _retrieval_phase_issues(
                transcript,
                overlay_request=overlay_request,
                run_dir=Path(run_dir),
            )
        )
        issues.extend(
            _solicitation_coverage_issues(
                payload,
                eval_entities_retrieved=int(stats["eval_entities_retrieved"]),
                run_dir=Path(run_dir),
            )
        )
        if payload is not None:
            issues.extend(_qualitative_depth_issues(payload, Path(run_dir)))

    if not _is_compiler_run(Path(run_dir)):
        finish_path = Path(run_dir) / "run.md"
        if finish_path.is_file():
            envelope = finish_path.read_text(encoding="utf-8", errors="replace")
            if "finish_reason: max_turns" in envelope or "forced_summary" in envelope:
                issues.append("run hit max_turns forced summary — output likely truncated")

    return issues


def _load_workspace_eval_entities(workspace_dir: Path) -> list[dict[str, Any]]:
    """Material evaluation_factor/subfactor entities from workspace VDB."""
    path = Path(workspace_dir) / "vdb_entities.json"
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    records: list[dict[str, Any]] = []
    if isinstance(raw, dict) and isinstance(raw.get("data"), list):
        records = [item for item in raw["data"] if isinstance(item, dict)]
    elif isinstance(raw, list):
        records = [item for item in raw if isinstance(item, dict)]

    entities: list[dict[str, Any]] = []
    for record in records:
        entity_type = str(record.get("entity_type") or "").strip().lower()
        if entity_type not in _EVAL_ENTITY_TYPES:
            continue
        name = str(
            record.get("entity_name")
            or record.get("name")
            or record.get("entity_id")
            or ""
        ).strip()
        if not _is_material_eval_factor(name):
            continue
        description = str(record.get("content") or record.get("description") or "").strip()
        if description.startswith(name):
            description = description[len(name) :].strip(" -—:")
        entities.append(
            {
                "name": name,
                "entity_type": entity_type,
                "description": description[:800],
            }
        )
    return entities


def _scratchpad_chunk_ids(run_dir: Path) -> list[str]:
    try:
        from src.skills.research_harness import load_harness_state
    except ImportError:
        return []
    state = load_harness_state(Path(run_dir))
    if not state:
        return []
    return [str(chunk_id) for chunk_id in (state.get("scratchpad_chunk_ids") or []) if chunk_id]


def record_missing_eval_crosswalk_gaps(
    payload: dict[str, Any],
    workspace_dir: Path,
) -> tuple[dict[str, Any], int]:
    """Record missing eval_crosswalk factors in claim_gaps[] — never inject scaffold rows."""
    entities = _load_workspace_eval_entities(workspace_dir)
    if not entities:
        return payload, 0

    crosswalk = payload.get("eval_crosswalk")
    if not isinstance(crosswalk, list):
        crosswalk = []
    existing_labels = {
        str(row.get("evaluation_factor") or "").strip().lower()
        for row in crosswalk
        if isinstance(row, dict) and str(row.get("evaluation_factor") or "").strip()
    }

    missing: list[str] = []
    for entity in entities:
        label = str(entity.get("name") or "").strip()
        if not label or label.lower() in existing_labels:
            continue
        missing.append(label)

    if missing:
        gaps = payload.get("claim_gaps")
        if not isinstance(gaps, list):
            gaps = []
        for label in missing:
            note = (
                f"eval_crosswalk: missing row for {label} — "
                "synthesize from scratchpad evidence with cited PWS clusters and proof"
            )
            if note not in gaps:
                gaps.append(note)
        payload["claim_gaps"] = gaps

    payload["eval_crosswalk"] = crosswalk
    return payload, len(missing)


def _minimal_frame_shell() -> dict[str, Any]:
    return {
        "opportunity_context": {
            "solicitation_id": "",
            "agency": "",
            "package_documents": [],
        },
        "mission_readiness_frame": {
            "readiness_outcome": "",
            "confidence": "medium",
            "source_chunk_ids": [],
            "failure_modes_feared": [],
            "workload_enablers": [],
            "readiness_signals": [],
            "our_read": "",
        },
        "customer_pain_points": [],
        "current_methods": [],
        "innovation_opportunities": [],
        "importance_signals": [],
        "implicit_criteria": [],
        "win_theme_candidates": [],
        "verbatim_extracts": [],
        "eval_crosswalk": [],
        "clarification_questions": [],
        "claim_gaps": [],
    }


def ensure_minimum_frame(
    run_dir: Path,
    workspace_dir: Path | None = None,
) -> Path | None:
    """Guarantee mission_readiness_frame.json exists; log missing eval rows in claim_gaps only."""
    artifacts = Path(run_dir) / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    frame_path = artifacts / "mission_readiness_frame.json"

    payload: dict[str, Any] = {}
    if frame_path.is_file():
        try:
            loaded = json.loads(frame_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, json.JSONDecodeError):
            payload = {}

    shell = _minimal_frame_shell()
    for key, default in shell.items():
        if key not in payload:
            payload[key] = default
        elif key == "mission_readiness_frame" and isinstance(payload.get(key), dict):
            frame = payload["mission_readiness_frame"]
            for sub_key, sub_default in shell["mission_readiness_frame"].items():
                if sub_key not in frame:
                    frame[sub_key] = sub_default

    for key in _REQUIRED_ARRAY_KEYS:
        if not isinstance(payload.get(key), list):
            payload[key] = []

    brief_path = artifacts / "brief.md"
    if brief_path.is_file() and not str(
        (payload.get("mission_readiness_frame") or {}).get("readiness_outcome") or ""
    ).strip():
        brief_text = brief_path.read_text(encoding="utf-8", errors="replace")
        match = re.search(
            r"\*\*Readiness Outcome\*\*:\s*(.+?)(?:\n\n|\[)",
            brief_text,
            re.DOTALL,
        )
        if match:
            payload.setdefault("mission_readiness_frame", {})["readiness_outcome"] = (
                match.group(1).strip()[:1200]
            )

    missing = 0
    if workspace_dir is not None:
        payload, missing = record_missing_eval_crosswalk_gaps(
            payload,
            Path(workspace_dir),
        )

    frame_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    state_note = (
        f"ensure_minimum_frame: ensured shell ({missing} eval factor gap(s) logged)"
        if missing
        else "ensure_minimum_frame: ensured minimum frame shell"
    )
    try:
        from src.skills.research_harness import load_harness_state, save_harness_state

        state = load_harness_state(Path(run_dir))
        if state is not None:
            notes = list(state.get("platform_notes") or [])
            if state_note not in notes:
                notes.append(state_note)
            state["platform_notes"] = notes[-20:]
            save_harness_state(Path(run_dir), state)
    except ImportError:
        pass
    return frame_path


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