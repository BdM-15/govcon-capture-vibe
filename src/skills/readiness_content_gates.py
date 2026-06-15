"""Shared substance and acronym quality gates for readiness-frame outputs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_BOILERPLATE_RE = re.compile(
    r"(?:"
    r"proposal must demonstrate compliant approach|"
    r"demonstrate compliant approach,\s*staffing,\s*and proof|"
    r"refine during capture review|"
    r"section m\s*/\s*pws task clusters|"
    r"auto-scaffolded from workspace|"
    r"weak performance on .+ degrades program readiness and eval confidence"
    r")",
    re.IGNORECASE,
)

_DEFINED_ACRONYM_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9'/\-\s]{2,60}\("
    r"([A-Z][A-Z0-9-]*(?:\s+[A-Z][A-Z0-9-]*)*[sS]?)"
    r"\)"
)

_HYPHEN_DESIGNATOR_RE = re.compile(
    r"\b[A-Za-z]+-([A-Z]{2,}(?:-[A-Z][A-Z0-9]*)?)\b",
    re.IGNORECASE,
)

_ACRONYM_TOKEN_RE = re.compile(r"\b[A-Z]{2,}(?:-[A-Z][A-Z0-9]*)?\b(?!\-\d)")

_VALID_CHUNK_ID_RE = re.compile(r"^(?:doc-|chunk-|tb-)[a-zA-Z0-9_-]+$", re.IGNORECASE)

_FORMULAIC_FACTOR_RE = re.compile(
    r"(?:"
    r"capset\s+production\s+subfactor|"
    r"section\s+m[-\s]*\d+.*\bfactor\b|"
    r"factor\s+\d+\s+cost/price|"
    r"subfactor\s+\d+\s*[-—]"
    r")",
    re.IGNORECASE,
)

_ONE_LINER_FIELD_RE = re.compile(
    r"^(?:.+ degrades program readiness|demonstrate compliant approach|refine during capture).{0,40}$",
    re.IGNORECASE,
)

_NARRATIVE_SECTION_MIN_CHARS = {
    "mission readiness frame": 350,
    "customer pain": 400,
    "importance signals": 300,
    "implicit criteria": 300,
    "current methods": 350,
    "win-theme": 250,
    "win theme": 250,
    "clarifications": 150,
}

_ACRONYM_ALLOWLIST = frozenset(
    {
        "ACR",
        "CDRL",
        "CLIN",
        "CONUS",
        "COR",
        "DFAR",
        "DLA",
        "DoD",
        "FAR",
        "FFP",
        "FPDS",
        "GSA",
        "IDIQ",
        "IMCOM",
        "IT",
        "JSON",
        "J&A",
        "KG",
        "NAICS",
        "OCONUS",
        "PCO",
        "POC",
        "PWS",
        "QASP",
        "RFP",
        "SOW",
        "TO",
        "UCF",
        "US",
        "USA",
        "USAF",
        "USMC",
        "USN",
        "NOT",
        "OUTSTANDING",
        "RELEVANT",
        "UNACCEPTABLE",
        "VERY",
    }
)

_KNOWN_ACRONYM_EXPANSIONS: dict[str, str] = {
    "CBA": "Collective Bargaining Agreement (CBA)",
    "CESE": "Commercial Electrical Support Equipment (CESE)",
    "CM": "Configuration Management (CM)",
    "CPARS": "Contractor Performance Assessment Reporting System (CPARS)",
    "CPFF": "Cost-Plus-Fixed-Fee (CPFF)",
    "FPRA": "Forward Pricing Rate Agreement (FPRA)",
    "IAW": "In Accordance With (IAW)",
    "NSC": "National Security Council (NSC)",
    "OGP": "Office of Government Procurement (OGP)",
    "PMCS": "Preventive Maintenance Checks and Services (PMCS)",
    "SB": "Small Business (SB)",
    "SDB": "Small Disadvantaged Business (SDB)",
    "TECV": "Total Evaluated Cost/Value (TECV)",
    "WBS": "Work Breakdown Structure (WBS)",
}


def is_boilerplate_text(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return bool(_BOILERPLATE_RE.search(text))


def defined_acronyms(text: str) -> set[str]:
    defined: set[str] = set()
    for match in _DEFINED_ACRONYM_RE.finditer(str(text or "")):
        for part in match.group(1).upper().split():
            defined.add(part)
            if part.endswith("S") and len(part) > 3:
                defined.add(part[:-1])
            if "-" in part:
                defined.add(part.split("-")[-1])
    for match in _HYPHEN_DESIGNATOR_RE.finditer(str(text or "")):
        suffix = match.group(1).upper()
        defined.add(suffix)
        if "-" in suffix:
            defined.add(suffix.split("-")[-1])
    for acronym in list(defined):
        if acronym.endswith("S") and len(acronym) > 3:
            defined.add(acronym[:-1])
        if "-" in acronym:
            defined.add(acronym.split("-")[-1])
    return defined


def undefined_acronyms(text: str) -> list[str]:
    defined = defined_acronyms(text)
    found: list[str] = []
    seen: set[str] = set()
    for token in _ACRONYM_TOKEN_RE.findall(str(text or "")):
        normalized = token.upper()
        if normalized in _ACRONYM_ALLOWLIST or normalized in defined:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        found.append(token)
    return found


def _is_valid_chunk_id(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text and _VALID_CHUNK_ID_RE.match(text))


def _normalize_factor_label(label: str) -> str:
    text = str(label or "").strip().lower()
    if not text:
        return ""
    return re.sub(
        r"\s*\((?:evaluation_factor|subfactor)\)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()


def _known_factor_labels(workspace_dir: Path | None) -> set[str]:
    if workspace_dir is None:
        return set()
    from src.skills.evidence_gates import load_material_eval_entities

    return {
        str(entity.get("name") or "").strip().lower()
        for entity in load_material_eval_entities(workspace_dir)
        if str(entity.get("name") or "").strip()
    }


def _factor_matches_inventory(label: str, known: set[str]) -> bool:
    normalized = _normalize_factor_label(label)
    if not normalized or not known:
        return False
    if normalized in known:
        return True
    return any(
        normalized in known_label or known_label in normalized for known_label in known
    )


def citation_issues_for_crosswalk_row(
    row: dict[str, Any],
    *,
    index: int,
    known_factor_labels: set[str] | None = None,
) -> list[str]:
    issues: list[str] = []
    factor = str(row.get("evaluation_factor") or "").strip()
    known = known_factor_labels or set()
    if (
        factor
        and _FORMULAIC_FACTOR_RE.search(factor)
        and not _factor_matches_inventory(factor, known)
    ):
        issues.append(
            f"eval_crosswalk row {index} evaluation_factor looks like invented shorthand "
            f"({factor!r}) — use verbatim Section M factor/subfactor names from evidence"
        )

    chunk_ids = row.get("source_chunk_ids") or []
    if not isinstance(chunk_ids, list) or not chunk_ids:
        issues.append(
            f"eval_crosswalk row {index} missing source_chunk_ids — cite doc-/chunk-/tb- IDs "
            "from scratchpad"
        )
        return issues

    invalid = [str(item) for item in chunk_ids if not _is_valid_chunk_id(item)]
    if invalid:
        sample = ", ".join(invalid[:3])
        suffix = "…" if len(invalid) > 3 else ""
        issues.append(
            f"eval_crosswalk row {index} has invalid source_chunk_ids ({sample}{suffix}) — "
            "use real doc-/chunk-/tb- IDs from retrieval, not invented labels"
        )
    return issues


def citation_diversity_issues_for_crosswalk(crosswalk: list[Any]) -> list[str]:
    primary_chunks: list[str] = []
    material = 0
    for row in crosswalk:
        if not isinstance(row, dict):
            continue
        factor = str(row.get("evaluation_factor") or "").strip()
        if not factor or factor.lower().startswith("entity:"):
            continue
        material += 1
        chunk_ids = row.get("source_chunk_ids") or []
        if isinstance(chunk_ids, list) and chunk_ids and _is_valid_chunk_id(chunk_ids[0]):
            primary_chunks.append(str(chunk_ids[0]).strip())
    if material < 8 or len(primary_chunks) < 8:
        return []
    counts: dict[str, int] = {}
    for chunk_id in primary_chunks:
        counts[chunk_id] = counts.get(chunk_id, 0) + 1
    top_chunk, top_count = max(counts.items(), key=lambda item: item[1])
    if top_count / len(primary_chunks) > 0.45:
        return [
            "eval_crosswalk over-relies on one source chunk "
            f"({top_chunk} in {top_count}/{len(primary_chunks)} rows) — "
            "diversify citations from scratchpad"
        ]
    return []


def _parse_markdown_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_key = ""
    buffer: list[str] = []
    for line in str(markdown or "").splitlines():
        if line.startswith("## "):
            if current_key:
                sections[current_key] = "\n".join(buffer).strip()
            current_key = line[3:].strip().lower()
            buffer = []
            continue
        if current_key:
            buffer.append(line)
    if current_key:
        sections[current_key] = "\n".join(buffer).strip()
    return sections


def _section_prose_chars(content: str) -> int:
    prose = 0
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|") or stripped.startswith("#"):
            continue
        if stripped.startswith(("- ", "* ")):
            prose += len(stripped)
        elif len(stripped) > 40:
            prose += len(stripped)
    return prose


def tail_compression_issues_for_brief(brief_text: str) -> list[str]:
    sections = _parse_markdown_sections(brief_text)
    if not sections:
        return []
    issues: list[str] = []
    for heading_key, minimum in _NARRATIVE_SECTION_MIN_CHARS.items():
        matched = next(
            (body for key, body in sections.items() if heading_key in key),
            "",
        )
        if not matched:
            continue
        prose_chars = _section_prose_chars(matched)
        if prose_chars < minimum:
            issues.append(
                f"brief section matching {heading_key!r} is compressed "
                f"({prose_chars} prose chars, need >={minimum}) — expand with "
                "multi-paragraph capture analysis consistent with earlier sections"
            )

    section_keys = list(sections.keys())
    if len(section_keys) >= 6:
        early = [
            _section_prose_chars(sections[key])
            for key in section_keys[:3]
            if "eval cross" not in key and "cross-walk" not in key
        ]
        late = [
            _section_prose_chars(sections[key])
            for key in section_keys[-3:]
            if "eval cross" not in key and "cross-walk" not in key and "overlay" not in key
        ]
        if early and late:
            early_avg = sum(early) / len(early)
            late_avg = sum(late) / len(late)
            if early_avg >= 500 and late_avg < early_avg * 0.35:
                issues.append(
                    "brief tail is compressed relative to front sections — maintain uniform "
                    "consultant-depth prose through win themes and clarifications"
                )
    return issues


_NARRATIVE_CITE_RE = re.compile(r"\[\d+\]")
_NARRATIVE_SECTION_HEADINGS = (
    "mission readiness",
    "customer pain",
    "importance signal",
    "implicit criteria",
    "current method",
    "innovation",
    "win theme",
    "win-theme",
    "executive synthesis",
)


def _brief_narrative_sections(brief_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_key = ""
    buffer: list[str] = []
    for line in str(brief_text or "").splitlines():
        if line.startswith("## "):
            if current_key:
                sections[current_key] = "\n".join(buffer).strip()
            current_key = line[3:].strip().lower()
            buffer = []
            continue
        if current_key:
            buffer.append(line)
    if current_key:
        sections[current_key] = "\n".join(buffer).strip()
    return sections


def narrative_citation_issues_for_brief(
    brief_text: str,
    *,
    payload: dict[str, Any] | None = None,
) -> list[str]:
    """Require numbered [N] markers in major narrative sections when references exist."""
    references = []
    if payload is not None:
        references = payload.get("references") or payload.get("source_citations") or []
    if not isinstance(references, list) or len(references) < 2:
        return []

    sections = _brief_narrative_sections(brief_text)
    if not sections:
        return []

    missing: list[str] = []
    for heading, body in sections.items():
        if "eval cross" in heading or "cross-walk" in heading or heading.startswith("references"):
            continue
        if "verbatim" in heading:
            continue
        if not any(token in heading for token in _NARRATIVE_SECTION_HEADINGS):
            continue
        prose = str(body or "").strip()
        if len(prose) < 120:
            continue
        if not _NARRATIVE_CITE_RE.search(prose):
            missing.append(heading)
    if len(missing) >= 3:
        sample = ", ".join(missing[:4])
        suffix = "…" if len(missing) > 4 else ""
        return [
            "brief.md narrative sections lack numbered citation markers [N] — "
            f"add refs in: {sample}{suffix}"
        ]
    return []


def verbatim_extract_issues(
    payload: dict[str, Any] | None,
    *,
    crosswalk_has_citations: bool,
    cited_crosswalk_rows: int = 0,
) -> list[str]:
    if not payload or not crosswalk_has_citations or cited_crosswalk_rows < 3:
        return []
    extracts = payload.get("verbatim_extracts") or []
    if isinstance(extracts, list) and extracts:
        return []
    return [
        "verbatim_extracts is empty — pull 3–8 short government quotes from scratchpad "
        "into mission_readiness_frame.json and brief.md verbatim bank"
    ]


def claim_gaps_brief_issues(
    payload: dict[str, Any] | None,
    brief_text: str,
) -> list[str]:
    if not payload:
        return []
    gaps = payload.get("claim_gaps")
    if not isinstance(gaps, list) or len(gaps) < 2:
        return []
    brief_lc = str(brief_text or "").lower()
    if "claim gap" in brief_lc or "missing coverage" in brief_lc or "clarifications" in brief_lc:
        reflected = 0
        for gap in gaps:
            snippet = str(gap or "").strip()[:48]
            if snippet and snippet.lower() in brief_lc:
                reflected += 1
        if reflected >= max(1, len(gaps) // 3):
            return []
    missing = 0
    for gap in gaps:
        snippet = str(gap or "").strip()[:40]
        if snippet and snippet.lower() not in brief_lc:
            missing += 1
    if missing >= max(2, int(len(gaps) * 0.5)):
        return [
            "brief.md does not reflect claim_gaps[] from JSON — add a Clarifications / "
            "missing-coverage section summarizing each logged gap"
        ]
    return []


def substance_issues_for_crosswalk_row(
    row: dict[str, Any],
    *,
    index: int,
    known_factor_labels: set[str] | None = None,
) -> list[str]:
    issues: list[str] = []
    readiness = str(row.get("readiness_link") or "").strip()
    proof = str(row.get("proof_expected") or "").strip()
    clusters = row.get("pws_clusters") or []
    cluster_text = " ".join(str(item) for item in clusters) if isinstance(clusters, list) else ""

    issues.extend(
        citation_issues_for_crosswalk_row(
            row,
            index=index,
            known_factor_labels=known_factor_labels,
        )
    )

    if len(readiness) < 60 and _ONE_LINER_FIELD_RE.match(readiness):
        issues.append(
            f"eval_crosswalk row {index} readiness_link is formulaic shorthand — "
            "write 2–4 sentences of consequence analysis"
        )
    if len(proof) < 50 and _ONE_LINER_FIELD_RE.match(proof):
        issues.append(
            f"eval_crosswalk row {index} proof_expected is formulaic shorthand — "
            "name concrete proof artifacts evaluators expect"
        )

    if is_boilerplate_text(readiness):
        issues.append(
            f"eval_crosswalk row {index} readiness_link is boilerplate — "
            "use customer terminology and cited rationale from scratchpad"
        )
    if is_boilerplate_text(proof):
        issues.append(
            f"eval_crosswalk row {index} proof_expected is boilerplate — "
            "name concrete proof artifacts evaluators expect"
        )
    if is_boilerplate_text(cluster_text):
        issues.append(
            f"eval_crosswalk row {index} pws_clusters is boilerplate — "
            "cite specific PWS/SOW task clusters from evidence"
        )
    return issues


_FRAME_ACRONYM_NARRATIVE_FIELDS = (
    "readiness_outcome",
    "scope_summary",
    "rationale",
    "readiness_link",
    "proof_expected",
    "description",
    "rationale_chain",
    "cited_rationale",
    "fit_to_scope",
    "summary",
    "signal",
    "criterion",
    "alternate_read",
    "quote",
    "text",
    "challenge_type",
    "pain_point",
    "latent_structural_challenge",
    "evaluation_factor",
)


def frame_narrative_text_for_acronym_gate(payload: dict[str, Any]) -> str:
    """Prose fields subject to acronym gate — excludes short structural labels."""
    parts: list[str] = []
    for key in ("readiness_outcome", "scope_summary"):
        parts.append(str(payload.get(key) or ""))
    for array_key in (
        "customer_pain_points",
        "current_methods",
        "innovation_opportunities",
        "importance_signals",
        "implicit_criteria",
        "win_theme_candidates",
        "verbatim_extracts",
        "clarification_questions",
        "eval_crosswalk",
    ):
        rows = payload.get(array_key) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, str):
                parts.append(row)
            elif isinstance(row, dict):
                for field in _FRAME_ACRONYM_NARRATIVE_FIELDS:
                    parts.append(str(row.get(field) or ""))
    gaps = payload.get("claim_gaps") or []
    if isinstance(gaps, list):
        parts.extend(str(gap) for gap in gaps if gap)
    return "\n".join(parts)


def acronym_issues_for_readiness_output(
    *,
    brief_text: str,
    payload: dict[str, Any] | None,
    label: str = "readiness output",
) -> list[str]:
    """Acronym gate across brief plus frame narrative fields (not label keys)."""
    narrative = frame_narrative_text_for_acronym_gate(payload) if payload else ""
    combined = f"{brief_text}\n{narrative}".strip()
    return acronym_issues_for_text(combined, label=label)


def acronym_issues_for_text(text: str, *, label: str) -> list[str]:
    undefined = undefined_acronyms(text)
    if not undefined:
        return []
    sample = ", ".join(undefined[:6])
    suffix = "…" if len(undefined) > 6 else ""
    return [
        f"{label}: undefined acronyms on first use — spell out as Full Term ({sample}{suffix})"
    ]


_EVAL_HANDOFF_ACRONYM_FIELDS = ("readiness_link", "proof_expected")


def eval_handoff_text_for_acronym_gate(payload: dict[str, Any]) -> str:
    """Prose fields for eval handoff acronym gate — excludes verbatim factor labels."""
    parts: list[str] = []
    crosswalk = payload.get("eval_crosswalk") or []
    if isinstance(crosswalk, list):
        for row in crosswalk:
            if not isinstance(row, dict):
                continue
            for field in _EVAL_HANDOFF_ACRONYM_FIELDS:
                parts.append(str(row.get(field) or ""))
    gaps = payload.get("claim_gaps") or []
    if isinstance(gaps, list):
        parts.extend(str(gap) for gap in gaps if gap)
    return "\n".join(parts)


def acronym_issues_for_eval_handoff(payload: dict[str, Any]) -> list[str]:
    return acronym_issues_for_text(
        eval_handoff_text_for_acronym_gate(payload),
        label="eval_handoff.json",
    )


def apply_known_acronym_expansions(text: str, *, targets: list[str] | None = None) -> str:
    """Deterministic first-use Full Term (ACR) expansion for common govcon tokens."""
    pending = targets or undefined_acronyms(text)
    revised = str(text or "")
    for token in pending:
        key = str(token or "").strip().upper()
        template = _KNOWN_ACRONYM_EXPANSIONS.get(key)
        if not template or key in defined_acronyms(revised):
            continue
        pattern = re.compile(rf"\b{re.escape(str(token))}\b")
        revised, count = pattern.subn(template, revised, count=1)
        if count:
            continue
    return revised


def apply_known_acronym_expansions_to_eval_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Expand known acronyms inside eval handoff narrative fields without an LLM."""
    if not isinstance(payload, dict):
        return payload
    targets = undefined_acronyms(eval_handoff_text_for_acronym_gate(payload))
    if not targets:
        return payload

    crosswalk = payload.get("eval_crosswalk")
    if isinstance(crosswalk, list):
        for row in crosswalk:
            if not isinstance(row, dict):
                continue
            for field in ("readiness_link", "proof_expected"):
                value = str(row.get(field) or "")
                if value:
                    row[field] = apply_known_acronym_expansions(value, targets=targets)

    gaps = payload.get("claim_gaps")
    if isinstance(gaps, list):
        payload["claim_gaps"] = [
            apply_known_acronym_expansions(str(gap or ""), targets=targets) for gap in gaps
        ]
    return payload


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z]{4,}", str(text or "").lower()))


def crosswalk_repetition_issues(
    crosswalk: list[Any],
    *,
    overlap_ratio: float = 0.62,
    max_similar_pairs: int = 2,
) -> list[str]:
    """Flag recycled readiness_link prose across factor rows (lazy duplicate research)."""
    tokenized: list[tuple[int, set[str]]] = []
    for index, row in enumerate(crosswalk, start=1):
        if not isinstance(row, dict):
            continue
        text = str(row.get("readiness_link") or "").strip()
        if len(text) < 80:
            continue
        tokens = _token_set(text)
        if len(tokens) >= 8:
            tokenized.append((index, tokens))

    similar_pairs = 0
    for left in range(len(tokenized)):
        for right in range(left + 1, len(tokenized)):
            left_tokens = tokenized[left][1]
            right_tokens = tokenized[right][1]
            if not left_tokens or not right_tokens:
                continue
            ratio = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
            if ratio >= overlap_ratio:
                similar_pairs += 1

    if similar_pairs > max_similar_pairs:
        return [
            f"eval_crosswalk has {similar_pairs} near-duplicate readiness_link pairs — "
            "each factor/subfactor row needs distinct consequence analysis grounded in "
            "that row's evidence, not recycled capture filler"
        ]
    return []


def substance_issues_for_crosswalk(
    crosswalk: list[Any],
    *,
    workspace_dir: Path | None = None,
) -> list[str]:
    issues: list[str] = []
    known = _known_factor_labels(workspace_dir)
    for index, raw in enumerate(crosswalk, start=1):
        if not isinstance(raw, dict):
            continue
        issues.extend(
            substance_issues_for_crosswalk_row(
                raw,
                index=index,
                known_factor_labels=known,
            )
        )
    issues.extend(citation_diversity_issues_for_crosswalk(crosswalk))
    issues.extend(crosswalk_repetition_issues(crosswalk))
    return issues


def substance_issues_for_frame_payload(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    crosswalk = payload.get("eval_crosswalk")
    if isinstance(crosswalk, list):
        issues.extend(substance_issues_for_crosswalk(crosswalk))
    return issues


def substance_issues_for_brief(
    brief_text: str,
    *,
    skip_tail_compression: bool = False,
) -> list[str]:
    issues = substance_issues_for_crosswalk_text_fields(brief_text)
    if not skip_tail_compression:
        issues.extend(tail_compression_issues_for_brief(brief_text))
    return issues


def compiler_output_substance_issues(run_dir: Path) -> list[str]:
    """Substance-only quality gate for chain compiler — not line/char counts."""
    artifacts = run_dir / "artifacts"
    frame_path = artifacts / "mission_readiness_frame.json"
    brief_path = artifacts / "brief.md"
    issues: list[str] = []

    if not brief_path.is_file():
        return ["compiler: missing artifacts/brief.md"]

    try:
        brief_text = brief_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ["compiler: brief.md unreadable"]

    payload: dict[str, Any] | None = None
    if frame_path.is_file():
        try:
            from src.skills.readiness_handoff_models import load_handoff_dict

            loaded = load_handoff_dict(frame_path)
            payload = loaded if isinstance(loaded, dict) else None
        except (OSError, json.JSONDecodeError, ValueError):
            issues.append("compiler: mission_readiness_frame.json unreadable")

    crosswalk = (payload or {}).get("eval_crosswalk") or []
    cited_rows = 0
    if isinstance(crosswalk, list):
        cited_rows = sum(
            1
            for row in crosswalk
            if isinstance(row, dict)
            and (row.get("source_chunk_ids") or row.get("source_citations"))
        )
    issues.extend(
        substance_issues_for_brief(brief_text, skip_tail_compression=False)
    )
    issues.extend(narrative_citation_issues_for_brief(brief_text, payload=payload))
    issues.extend(
        verbatim_extract_issues(
            payload,
            crosswalk_has_citations=cited_rows > 0,
            cited_crosswalk_rows=cited_rows,
        )
    )
    issues.extend(claim_gaps_brief_issues(payload, brief_text))
    issues.extend(acronym_issues_for_readiness_output(brief_text=brief_text, payload=payload))

    pains = (payload or {}).get("customer_pain_points") or []
    if isinstance(pains, list):
        cited = [
            row
            for row in pains
            if isinstance(row, dict)
            and (row.get("source_chunk_ids") or row.get("source_citations"))
        ]
        if len(pains) >= 3 and len(cited) < max(2, len(pains) // 2):
            issues.append(
                "compiler: customer_pain_points lack cited rationale — each material pain "
                "needs source_chunk_ids from package evidence"
            )

    return issues


def substance_issues_for_frame_and_brief(
    payload: dict[str, Any] | None,
    brief_text: str,
    *,
    skip_tail_compression: bool = False,
) -> list[str]:
    issues: list[str] = []
    if payload is not None:
        issues.extend(substance_issues_for_frame_payload(payload))
    issues.extend(
        substance_issues_for_brief(brief_text, skip_tail_compression=skip_tail_compression)
    )
    issues.extend(claim_gaps_brief_issues(payload, brief_text))
    issues.extend(narrative_citation_issues_for_brief(brief_text, payload=payload))
    crosswalk = (payload or {}).get("eval_crosswalk") or []
    cited_rows = 0
    if isinstance(crosswalk, list):
        cited_rows = sum(
            1
            for row in crosswalk
            if isinstance(row, dict)
            and (row.get("source_chunk_ids") or row.get("source_citations"))
        )
    crosswalk_has_citations = cited_rows > 0
    issues.extend(
        verbatim_extract_issues(
            payload,
            crosswalk_has_citations=crosswalk_has_citations,
            cited_crosswalk_rows=cited_rows,
        )
    )
    return issues


def substance_issues_for_crosswalk_text_fields(text: str) -> list[str]:
    issues: list[str] = []
    if is_boilerplate_text(text):
        issues.append(
            "brief or crosswalk contains boilerplate capture filler — "
            "replace with customer-grounded reasoning and cited proof"
        )
    return issues


def validate_eval_handoff_write(
    *,
    path: str,
    content: str,
) -> str | None:
    cleaned = str(path or "").replace("\\", "/").split("/")[-1].lower()
    if cleaned != "eval_handoff.json":
        return None
    try:
        loaded = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return "eval_handoff.json must be a JSON object"
    crosswalk = loaded.get("eval_crosswalk")
    if not isinstance(crosswalk, list):
        return None
    for index, row in enumerate(crosswalk, start=1):
        if not isinstance(row, dict):
            continue
        if str(row.get("factor") or row.get("subfactor") or "").strip() and not str(
            row.get("evaluation_factor") or ""
        ).strip():
            return (
                "write_file blocked for eval_handoff.json: eval_crosswalk row "
                f"{index} uses legacy factor/subfactor shape — emit evaluation_factor, "
                "readiness_link, proof_expected, and pws_clusters per readiness_output_contract.md"
            )
        for issue in substance_issues_for_crosswalk_row(row, index=index):
            return f"write_file blocked for eval_handoff.json: {issue}"
    issues = citation_diversity_issues_for_crosswalk(crosswalk)
    if issues:
        return f"write_file blocked for eval_handoff.json: {issues[0]}"
    for issue in acronym_issues_for_eval_handoff(loaded):
        return f"write_file blocked for eval_handoff.json: {issue}"
    return None