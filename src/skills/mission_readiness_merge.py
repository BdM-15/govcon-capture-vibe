"""Deterministic merge of readiness-frame micro-skill handoffs for chain compile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from src.skills.source_citations import (
    enrich_payload_citations,
    format_citations_for_prose,
    format_citations_for_table,
    format_references_section,
    resolve_workspace_dir_from_run_dir,
)

_HANDOFF_FILENAMES: dict[str, str] = {
    "eval_handoff.json": "eval",
    "workload_handoff.json": "workload",
    "pains_handoff.json": "pains",
    "modernization_handoff.json": "modernization",
    "tea_leaves_handoff.json": "tea_leaves",
    "win_themes_handoff.json": "win_themes",
    "capability_overlay_handoff.json": "external",
}

_ARRAY_KEYS = (
    "customer_pain_points",
    "current_methods",
    "innovation_opportunities",
    "importance_signals",
    "implicit_criteria",
    "win_theme_candidates",
    "verbatim_extracts",
    "clarification_questions",
    "claim_gaps",
)

_FRAME_ARRAY_KEYS = (
    "failure_modes_feared",
    "workload_enablers",
    "readiness_signals",
)

_COMPILER_SCRATCHPAD_MAX_CHARS = 500_000
_UPSTREAM_SCRATCHPAD_SLICE_CAP = 120_000


def is_compiler_chain_context(entity_payload: dict[str, Any] | None) -> bool:
    ctx = (entity_payload or {}).get("chain_step_context") or {}
    return str(ctx.get("role") or "").strip().lower() == "compiler"


def is_compiler_run_dir(run_dir: Path) -> bool:
    ctx_path = Path(run_dir) / "artifacts" / "chain_context.json"
    if not ctx_path.is_file():
        return False
    try:
        loaded = json.loads(ctx_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(loaded, dict) and str(loaded.get("role") or "").strip().lower() == "compiler"


def normalize_eval_crosswalk_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map legacy factor/subfactor/plain_reasoning rows to contract field names."""
    factor = str(row.get("factor") or "").strip()
    subfactor = str(row.get("subfactor") or "").strip()
    evaluation_factor = str(row.get("evaluation_factor") or "").strip()
    if not evaluation_factor:
        if subfactor and factor:
            evaluation_factor = f"{factor} — {subfactor}"
        else:
            evaluation_factor = subfactor or factor

    eval_narrative = str(row.get("evaluation_crosswalk") or "").strip()
    plain = str(row.get("plain_reasoning") or "").strip()
    readiness = str(row.get("readiness_link") or "").strip()
    if not readiness:
        readiness = eval_narrative or plain

    proof = str(row.get("proof_expected") or "").strip()
    if not proof and eval_narrative and eval_narrative != readiness:
        proof = eval_narrative
    elif not proof and plain and plain != readiness:
        proof = plain
    elif not proof and evaluation_factor:
        proof = (
            f"Proposal volume proof aligned to {evaluation_factor}: methodology, "
            "staffing, past performance, and Section L compliance artifacts."
        )

    clusters = row.get("pws_clusters")
    if not isinstance(clusters, list):
        clusters = []

    normalized: dict[str, Any] = {
        "evaluation_factor": evaluation_factor,
        "pws_clusters": clusters,
        "readiness_link": readiness,
        "proof_expected": proof,
        "source_chunk_ids": list(row.get("source_chunk_ids") or []),
    }
    for key in ("source_citations", "references"):
        if key in row:
            normalized[key] = row[key]
    return normalized


def _load_handoff_payload(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _resolve_handoff_path(artifact: dict[str, Any]) -> Path | None:
    raw_path = str(artifact.get("path") or "").strip()
    if raw_path:
        candidate = Path(raw_path)
        if candidate.is_file():
            return candidate
    filename = str(artifact.get("filename") or "").strip()
    if not filename:
        return None
    return None


def _dedupe_rows(rows: list[Any], *, key_fn: Callable[[dict[str, Any]], str]) -> list[Any]:
    seen: set[str] = set()
    deduped: list[Any] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        key = key_fn(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(raw)
    return deduped


def _union_extend(target: list[Any], source: Any) -> None:
    if not isinstance(source, list):
        return
    target.extend(item for item in source if item is not None)


def _merge_frame_dict(base: dict[str, Any], incoming: Any) -> dict[str, Any]:
    if not isinstance(incoming, dict):
        return base
    for key, value in incoming.items():
        if key in _FRAME_ARRAY_KEYS and isinstance(value, list):
            existing = base.get(key)
            if not isinstance(existing, list):
                base[key] = list(value)
            else:
                existing.extend(value)
        elif value not in (None, "", [], {}):
            if key not in base or base[key] in (None, "", [], {}):
                base[key] = value
            elif isinstance(base[key], dict) and isinstance(value, dict):
                merged = dict(base[key])
                merged.update(value)
                base[key] = merged
    return base


def _item_key(row: dict[str, Any]) -> str:
    for field in ("id", "theme_id", "enabler", "mode", "name", "theme_name", "signal", "criterion"):
        value = str(row.get(field) or "").strip()
        if value:
            return value.lower()
    return json.dumps(row, sort_keys=True, ensure_ascii=False)


def merge_handoff_payloads(handoffs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Merge loaded handoff dicts keyed by slice id into a frame envelope."""
    frame: dict[str, Any] = {}
    opportunity_context: dict[str, Any] = {}
    arrays: dict[str, list[Any]] = {key: [] for key in _ARRAY_KEYS}
    crosswalk: list[dict[str, Any]] = []
    capability_overlay: dict[str, Any] | None = None

    eval_payload = handoffs.get("eval") or {}
    for raw in eval_payload.get("eval_crosswalk") or []:
        if isinstance(raw, dict):
            crosswalk.append(normalize_eval_crosswalk_row(raw))
    _union_extend(arrays["claim_gaps"], eval_payload.get("claim_gaps"))

    workload = handoffs.get("workload") or {}
    _merge_frame_dict(frame, workload.get("mission_readiness_frame"))
    if isinstance(workload.get("opportunity_context"), dict):
        opportunity_context.update(workload["opportunity_context"])

    pains = handoffs.get("pains") or {}
    _merge_frame_dict(frame, pains.get("mission_readiness_frame"))
    if isinstance(pains.get("opportunity_context"), dict):
        for key, value in pains["opportunity_context"].items():
            if key not in opportunity_context:
                opportunity_context[key] = value
    _union_extend(arrays["customer_pain_points"], pains.get("customer_pain_points"))
    _union_extend(arrays["verbatim_extracts"], pains.get("verbatim_extracts"))
    _union_extend(arrays["clarification_questions"], pains.get("clarification_questions"))
    _union_extend(arrays["claim_gaps"], pains.get("claim_gaps"))

    modernization = handoffs.get("modernization") or {}
    if isinstance(modernization.get("mission_readiness_frame"), str):
        frame.setdefault("scope_summary", modernization["mission_readiness_frame"])
    _union_extend(arrays["current_methods"], modernization.get("current_methods"))
    _union_extend(arrays["innovation_opportunities"], modernization.get("innovation_opportunities"))
    _union_extend(arrays["claim_gaps"], modernization.get("claim_gaps"))

    tea = handoffs.get("tea_leaves") or {}
    tea_block = tea.get("tea_leaves")
    if isinstance(tea_block, dict):
        _union_extend(arrays["importance_signals"], tea_block.get("importance_signals"))
        _union_extend(arrays["implicit_criteria"], tea_block.get("implicit_criteria"))
        _union_extend(arrays["claim_gaps"], tea_block.get("claim_gaps"))
    else:
        _union_extend(arrays["importance_signals"], tea.get("importance_signals"))
        _union_extend(arrays["implicit_criteria"], tea.get("implicit_criteria"))
        _union_extend(arrays["claim_gaps"], tea.get("claim_gaps"))

    win = handoffs.get("win_themes") or {}
    _merge_frame_dict(frame, win.get("mission_readiness_frame"))
    if isinstance(win.get("opportunity_context"), dict):
        for key, value in win["opportunity_context"].items():
            if key not in opportunity_context:
                opportunity_context[key] = value
    _union_extend(arrays["win_theme_candidates"], win.get("win_theme_candidates"))
    _union_extend(arrays["claim_gaps"], win.get("claim_gaps"))

    external = handoffs.get("external") or {}
    overlay = external.get("capability_overlay")
    if isinstance(overlay, dict):
        capability_overlay = overlay

    crosswalk = _dedupe_rows(
        crosswalk,
        key_fn=lambda row: str(row.get("evaluation_factor") or "").strip().lower(),
    )
    for key in _ARRAY_KEYS:
        if key == "claim_gaps":
            arrays[key] = list(dict.fromkeys(str(item).strip() for item in arrays[key] if str(item).strip()))
        else:
            arrays[key] = _dedupe_rows(arrays[key], key_fn=_item_key)

    merged: dict[str, Any] = dict(frame)
    merged["eval_crosswalk"] = crosswalk
    for key, value in arrays.items():
        if value:
            merged[key] = value
    if opportunity_context:
        merged["opportunity_context"] = opportunity_context
    if capability_overlay:
        merged["capability_overlay"] = capability_overlay
    for key in (
        "customer_pain_points",
        "current_methods",
        "innovation_opportunities",
        "importance_signals",
        "implicit_criteria",
        "win_theme_candidates",
        "verbatim_extracts",
        "eval_crosswalk",
        "clarification_questions",
        "claim_gaps",
    ):
        if not isinstance(merged.get(key), list):
            merged[key] = []
    merged["merge_provenance"] = {
        "slices": sorted(handoffs.keys()),
        "eval_crosswalk_rows": len(crosswalk),
    }
    return merged


_SEED_VERBATIM_ARRAY_KEYS = (
    "eval_crosswalk",
    "customer_pain_points",
    "importance_signals",
    "implicit_criteria",
    "current_methods",
    "innovation_opportunities",
    "win_theme_candidates",
)

_MIN_VERBATIM_QUOTE_CHARS = 18
_MAX_VERBATIM_EXTRACTS = 8


def seed_verbatim_extracts_from_citations(payload: dict[str, Any]) -> dict[str, Any]:
    """Populate verbatim_extracts[] from source_citations quotes when merge left it empty."""
    if not isinstance(payload, dict):
        return payload
    existing = payload.get("verbatim_extracts") or []
    if isinstance(existing, list) and existing:
        return payload

    seen_quotes: set[str] = set()
    extracts: list[dict[str, Any]] = []

    for array_key in _SEED_VERBATIM_ARRAY_KEYS:
        rows = payload.get(array_key) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            citations = row.get("source_citations") or []
            if not isinstance(citations, list):
                continue
            for citation in citations:
                if not isinstance(citation, dict):
                    continue
                quote = str(citation.get("quote") or "").strip()
                if len(quote) < _MIN_VERBATIM_QUOTE_CHARS:
                    continue
                dedupe_key = quote.lower()
                if dedupe_key in seen_quotes:
                    continue
                seen_quotes.add(dedupe_key)
                chunk_id = str(citation.get("chunk_id") or "").strip()
                section = str(citation.get("section") or "").strip()
                entry: dict[str, Any] = {
                    "id": f"VE-{len(extracts) + 1:03d}",
                    "quote": quote,
                    "source_chunk_ids": [chunk_id] if chunk_id else [],
                }
                if section:
                    entry["section"] = section
                extracts.append(entry)
                if len(extracts) >= _MAX_VERBATIM_EXTRACTS:
                    payload["verbatim_extracts"] = extracts
                    return payload

    if extracts:
        payload["verbatim_extracts"] = extracts
    return payload


_COMPILER_FRAME_ARRAY_KEYS = (
    "customer_pain_points",
    "current_methods",
    "innovation_opportunities",
    "importance_signals",
    "implicit_criteria",
    "win_theme_candidates",
    "verbatim_extracts",
    "eval_crosswalk",
    "clarification_questions",
    "claim_gaps",
)


def normalize_compiler_frame_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Ensure merged compiler frames always expose required list keys."""
    normalized = dict(payload)
    for key in _COMPILER_FRAME_ARRAY_KEYS:
        rows = normalized.get(key)
        if not isinstance(rows, list):
            normalized[key] = []
    return normalized


def persist_normalized_compiler_frame(run_dir: Path) -> bool:
    """Normalize mission_readiness_frame.json list keys for compiler validation."""
    if not is_compiler_run_dir(run_dir):
        return False
    artifacts_dir = Path(run_dir) / "artifacts"
    frame_path = artifacts_dir / "mission_readiness_frame.json"
    if not frame_path.is_file():
        return False
    try:
        loaded = json.loads(frame_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(loaded, dict):
        return False
    normalized = normalize_compiler_frame_envelope(loaded)
    crosswalk = normalized.get("eval_crosswalk")
    if isinstance(crosswalk, list) and crosswalk:
        normalized["eval_crosswalk"] = [
            normalize_eval_crosswalk_row(row) if isinstance(row, dict) else row
            for row in crosswalk
        ]
    workspace_dir = resolve_workspace_dir_from_run_dir(run_dir)
    if workspace_dir is not None:
        normalized = enrich_payload_citations(normalized, workspace_dir)
    if normalized == loaded:
        return False
    frame_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def _upstream_scratchpad_for_artifact(artifact: dict[str, Any]) -> Path | None:
    filename = str(artifact.get("filename") or "").strip().lower()
    if filename not in _HANDOFF_FILENAMES:
        return None
    raw = str(artifact.get("path") or "").strip()
    if not raw:
        return None
    scratchpad = Path(raw).parent / "research_scratchpad.md"
    return scratchpad if scratchpad.is_file() else None


def _build_compiler_scratchpad(
    attached_artifacts: list[dict[str, Any]],
    handoffs: dict[str, dict[str, Any]],
    merged: dict[str, Any],
    *,
    max_chars: int = _COMPILER_SCRATCHPAD_MAX_CHARS,
) -> str:
    """Merge upstream slice scratchpads + handoff JSON for compiler synthesis."""
    sections: list[str] = [
        "# Chain compiler — upstream retrieval evidence corpus",
        "",
        "Synthesis MUST mine these scratchpads for multi-paragraph analytical prose, ",
        "verbatim government quotes, and diversified citations. Merged JSON handoffs ",
        "are the structural spine — not a substitute for scratchpad evidence.",
        "",
    ]
    seen_runs: set[str] = set()
    total_chars = len("\n".join(sections))

    for artifact in attached_artifacts:
        if not isinstance(artifact, dict):
            continue
        run_id = str(artifact.get("run_id") or "").strip()
        if run_id and run_id in seen_runs:
            continue
        scratchpad_path = _upstream_scratchpad_for_artifact(artifact)
        if scratchpad_path is None:
            continue
        if run_id:
            seen_runs.add(run_id)
        step_id = str(
            artifact.get("step_id") or artifact.get("skill") or "upstream_slice"
        ).strip()
        body = scratchpad_path.read_text(encoding="utf-8", errors="replace").strip()
        if len(body) > _UPSTREAM_SCRATCHPAD_SLICE_CAP:
            body = (
                body[:_UPSTREAM_SCRATCHPAD_SLICE_CAP]
                + "\n\n…[upstream scratchpad truncated per slice]\n"
            )
        block = f"## Upstream retrieval: {step_id}\n\n{body}\n"
        if total_chars + len(block) > max_chars:
            sections.append(
                f"\n…[scratchpad corpus capped at {max_chars} chars after "
                f"{len(seen_runs)} upstream run(s)]\n"
            )
            break
        sections.append(block)
        total_chars += len(block)

    sections.extend(
        [
            "## Merged handoff summary",
            "",
            f"Merged {len(handoffs)} handoff slice(s): {', '.join(sorted(handoffs.keys()))}.",
            f"Material eval_crosswalk rows: {len(merged.get('eval_crosswalk') or [])}.",
            "",
        ]
    )
    for slice_id, payload in sorted(handoffs.items()):
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(serialized) > 32_000:
            serialized = serialized[:32_000] + "\n…[handoff JSON truncated]\n"
        sections.extend(
            [
                f"### Handoff JSON: {slice_id}",
                "```json",
                serialized,
                "```",
                "",
            ]
        )
    return "\n".join(sections).strip() + "\n"


def merge_upstream_handoffs(
    attached_artifacts: list[dict[str, Any]],
    run_dir: Path,
    *,
    chain_step_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load handoff JSON from attached chain artifacts and write merged compiler outputs."""
    artifacts_dir = Path(run_dir) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    handoffs: dict[str, dict[str, Any]] = {}
    manifest: list[dict[str, Any]] = []

    for artifact in attached_artifacts:
        if not isinstance(artifact, dict):
            continue
        filename = str(artifact.get("filename") or "").strip().lower()
        slice_id = _HANDOFF_FILENAMES.get(filename)
        if not slice_id:
            continue
        path = _resolve_handoff_path(artifact)
        if path is None:
            raw_path = str(artifact.get("path") or "").strip()
            if raw_path:
                path = Path(raw_path)
        if path is None or not path.is_file():
            manifest.append(
                {
                    "slice": slice_id,
                    "filename": filename,
                    "status": "missing",
                    "path": str(artifact.get("path") or ""),
                }
            )
            continue
        payload = _load_handoff_payload(path)
        if payload is None:
            manifest.append({"slice": slice_id, "filename": filename, "status": "invalid", "path": str(path)})
            continue
        handoffs[slice_id] = payload
        manifest.append(
            {
                "slice": slice_id,
                "filename": filename,
                "status": "loaded",
                "path": str(path),
                "step_id": artifact.get("step_id"),
                "skill": artifact.get("skill"),
                "run_id": artifact.get("run_id"),
            }
        )

    merged = normalize_compiler_frame_envelope(merge_handoff_payloads(handoffs))
    workspace_dir = resolve_workspace_dir_from_run_dir(run_dir)
    if workspace_dir is not None:
        merged = enrich_payload_citations(merged, workspace_dir)
    merged = seed_verbatim_extracts_from_citations(merged)
    from src.skills.readiness_content_gates import apply_known_acronym_expansions_to_frame_payload

    merged = apply_known_acronym_expansions_to_frame_payload(merged)
    frame_path = artifacts_dir / "mission_readiness_frame.json"
    frame_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    chain_context = {
        "role": str((chain_step_context or {}).get("role") or "compiler"),
        "step_context": chain_step_context or {},
        "handoff_manifest": manifest,
        "merged_slices": sorted(handoffs.keys()),
        "eval_crosswalk_rows": len(merged.get("eval_crosswalk") or []),
    }
    (artifacts_dir / "chain_context.json").write_text(
        json.dumps(chain_context, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    scratchpad_text = _build_compiler_scratchpad(attached_artifacts, handoffs, merged)
    scratchpad_path = artifacts_dir / "research_scratchpad.md"
    scratchpad_path.write_text(scratchpad_text, encoding="utf-8")
    write_compiler_brief_scaffold(run_dir, merged=merged)

    merge_report = {
        "handoffs_loaded": len(handoffs),
        "manifest": manifest,
        "eval_crosswalk_rows": len(merged.get("eval_crosswalk") or []),
        "array_counts": {
            key: len(merged.get(key) or [])
            for key in _ARRAY_KEYS
        },
    }
    (artifacts_dir / "handoff_merge_report.json").write_text(
        json.dumps(merge_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return merge_report


def _escape_table_cell(value: Any, *, limit: int = 400) -> str:
    text = str(value or "").strip().replace("|", "/").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _format_eval_crosswalk_table(crosswalk: list[Any]) -> str:
    lines = [
        "| Evaluation Factor | Readiness Link | Proof Expected | Sources |",
        "| --- | --- | --- | --- |",
    ]
    for row in crosswalk:
        if not isinstance(row, dict):
            continue
        factor = _escape_table_cell(row.get("evaluation_factor"), limit=120)
        if not factor:
            continue
        readiness = _escape_table_cell(row.get("readiness_link"))
        proof = _escape_table_cell(row.get("proof_expected"))
        citations = row.get("source_citations") or []
        if isinstance(citations, list) and citations:
            sources = _escape_table_cell(format_citations_for_table(citations), limit=500)
        else:
            sources = ", ".join(
                _escape_table_cell(chunk_id, limit=80)
                for chunk_id in (row.get("source_chunk_ids") or [])[:4]
                if str(chunk_id or "").strip()
            )
        lines.append(f"| {factor} | {readiness} | {proof} | {sources} |")
    return "\n".join(lines) if len(lines) > 2 else "_No eval_crosswalk rows in merged frame._"


def _format_bullet_items(rows: list[Any], *, fields: tuple[str, ...]) -> str:
    bullets: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parts = [
            str(row.get(field) or "").strip()
            for field in fields
            if str(row.get(field) or "").strip()
        ]
        citations = row.get("source_citations") or []
        if isinstance(citations, list) and citations:
            cite_text = format_citations_for_prose(citations)
            if cite_text:
                parts.append(cite_text)
        if parts:
            bullets.append("- " + " — ".join(parts))
    return "\n".join(bullets) if bullets else "_None recorded in merged handoffs._"


def write_compiler_brief_scaffold(
    run_dir: Path,
    *,
    merged: dict[str, Any] | None = None,
) -> Path:
    """Seed brief.md with required sections + eval table before compiler synthesis."""
    artifacts_dir = Path(run_dir) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    if merged is None:
        frame_path = artifacts_dir / "mission_readiness_frame.json"
        if not frame_path.is_file():
            raise FileNotFoundError(f"Missing merged frame: {frame_path}")
        loaded = json.loads(frame_path.read_text(encoding="utf-8"))
        merged = loaded if isinstance(loaded, dict) else {}

    readiness = str(merged.get("readiness_outcome") or "").strip()
    enablers = merged.get("workload_enablers") or []
    if isinstance(enablers, list):
        enabler_text = "\n".join(f"- {str(item).strip()}" for item in enablers if str(item).strip())
    else:
        enabler_text = ""

    crosswalk = merged.get("eval_crosswalk") or []
    gaps = merged.get("claim_gaps") or []
    gap_lines = "\n".join(f"- {str(gap).strip()}" for gap in gaps if str(gap).strip())

    sections = [
        "# Mission Readiness Frame Brief (chain compiler)",
        "",
        "## 1. Mission Readiness Frame",
        "",
        readiness or "_Expand readiness outcome from merged mission_readiness_frame.json._",
        "",
        enabler_text,
        "",
        "## 2. Verbatim Signal Bank (Government Language)",
        "",
        _format_bullet_items(merged.get("verbatim_extracts") or [], fields=("quote", "signal", "text")),
        "",
        "## 3. Customer Pain Points & Importance Signals",
        "",
        "### Customer pains",
        _format_bullet_items(
            merged.get("customer_pain_points") or [],
            fields=("challenge_type", "rationale", "readiness_link"),
        ),
        "",
        "### Importance signals",
        _format_bullet_items(
            merged.get("importance_signals") or [],
            fields=("signal", "rationale"),
        ),
        "",
        "## 4. Current Methods vs. Innovation Opportunities",
        "",
        "### Current methods",
        _format_bullet_items(merged.get("current_methods") or [], fields=("name", "summary", "fit_to_scope")),
        "",
        "### Innovation opportunities",
        _format_bullet_items(
            merged.get("innovation_opportunities") or [],
            fields=("theme", "fit_to_scope", "rationale"),
        ),
        "",
        "## 5. Evaluation Cross-Walk Table (One Row per Material Factor/Subfactor)",
        "",
        _format_eval_crosswalk_table(crosswalk if isinstance(crosswalk, list) else []),
        "",
        "## 6. Implicit Criteria / Tea Leaves",
        "",
        _format_bullet_items(
            merged.get("implicit_criteria") or [],
            fields=("criterion", "rationale", "alternate_read"),
        ),
        "",
        "## 7. Win-Theme Candidate Spine (Priority-Ranked)",
        "",
        _format_bullet_items(
            merged.get("win_theme_candidates") or [],
            fields=("theme", "title", "theme_name", "rationale_chain"),
        ),
        "",
        "## 8. Clarification Questions + Claim Gaps",
        "",
        gap_lines or "_No claim_gaps logged._",
        "",
        "## Executive Synthesis",
        "",
        "_Tie readiness outcome to top win themes after expanding all sections above._",
        "",
        format_references_section(merged.get("references") or []),
        "",
    ]
    brief_path = artifacts_dir / "brief.md"
    brief_path.write_text("\n".join(sections), encoding="utf-8")
    return brief_path


def refresh_compiler_verbatim_section(
    run_dir: Path,
    *,
    payload: dict[str, Any] | None = None,
) -> None:
    """Sync brief.md §2 verbatim bank from frame verbatim_extracts[]."""
    artifacts_dir = Path(run_dir) / "artifacts"
    frame_path = artifacts_dir / "mission_readiness_frame.json"
    brief_path = artifacts_dir / "brief.md"
    if not brief_path.is_file():
        return
    if payload is None:
        if not frame_path.is_file():
            return
        try:
            loaded = json.loads(frame_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        payload = loaded if isinstance(loaded, dict) else None
    if not isinstance(payload, dict):
        return
    extracts = payload.get("verbatim_extracts") or []
    if not isinstance(extracts, list) or not extracts:
        return

    verbatim_block = _format_bullet_items(extracts, fields=("quote", "signal", "text"))
    section = (
        "## 2. Verbatim Signal Bank (Government Language)\n\n"
        f"{verbatim_block}\n"
    )
    try:
        brief = brief_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    marker = "## 2. Verbatim Signal Bank (Government Language)"
    if marker not in brief:
        return
    start = brief.index(marker)
    end = len(brief)
    for heading in ("## 3.", "## 4.", "## 5."):
        idx = brief.find(heading, start + len(marker))
        if idx > start:
            end = idx
            break
    brief = brief[:start] + section + brief[end:]
    brief_path.write_text(brief.strip() + "\n", encoding="utf-8")


def refresh_compiler_claim_gaps_section(run_dir: Path) -> None:
    """Ensure brief.md section 8 lists every claim_gaps[] entry from merged frame."""
    artifacts_dir = Path(run_dir) / "artifacts"
    frame_path = artifacts_dir / "mission_readiness_frame.json"
    brief_path = artifacts_dir / "brief.md"
    if not frame_path.is_file() or not brief_path.is_file():
        return
    try:
        payload = json.loads(frame_path.read_text(encoding="utf-8"))
        brief = brief_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict):
        return
    gaps = payload.get("claim_gaps") or []
    if not isinstance(gaps, list) or not gaps:
        return

    gap_block = "\n".join(f"- {str(gap).strip()}" for gap in gaps if str(gap).strip())
    section = (
        "## 8. Clarification Questions + Claim Gaps\n\n"
        "The following gaps were logged during upstream slice retrieval and merge. "
        "They are honest deferrals — not placeholders.\n\n"
        f"{gap_block}\n"
    )
    markers = (
        "## 8. Clarification Questions + Claim Gaps",
        "## 8. Clarifications / Missing-Coverage Section",
    )
    replaced = False
    for marker in markers:
        if marker in brief:
            start = brief.index(marker)
            end = len(brief)
            for heading in ("## 9.", "## Executive Synthesis", "## 8."):
                if heading == marker:
                    continue
                idx = brief.find(heading, start + len(marker))
                if idx > start:
                    end = idx
                    break
            brief = brief[:start] + section + brief[end:]
            replaced = True
            break
    if not replaced:
        brief = brief.rstrip() + "\n\n" + section
    brief_path.write_text(brief.strip() + "\n", encoding="utf-8")


def prepare_compiler_harness_state(run_dir: Path, *, scratchpad_chars: int) -> None:
    """Mark harness retrieval complete for chain compiler runs."""
    from src.skills.research_harness import load_harness_state, save_harness_state
    from src.skills.research_plan import sync_plan_file

    state = load_harness_state(run_dir)
    if not state:
        return
    state["phase"] = "draft"
    state["kg_entities_satisfied"] = True
    state["plan_surfaces"] = [
        {
            "id": "compiler_handoff_merge",
            "label": "Upstream readiness handoffs (deterministic merge)",
            "status": "retrieved",
            "kg_chunks_attempts": 0,
            "last_new_chunks": 0,
        }
    ]
    state["scratchpad_chars"] = scratchpad_chars
    state["bootstrap_seeded"] = True
    notes = list(state.get("platform_notes") or [])
    note = "compiler_mode: retrieval skipped — upstream handoffs merged deterministically"
    if note not in notes:
        notes.append(note)
    state["platform_notes"] = notes[-20:]
    save_harness_state(run_dir, state)
    sync_plan_file(run_dir, state)


__all__ = [
    "is_compiler_chain_context",
    "is_compiler_run_dir",
    "merge_handoff_payloads",
    "merge_upstream_handoffs",
    "normalize_compiler_frame_envelope",
    "normalize_eval_crosswalk_row",
    "persist_normalized_compiler_frame",
    "prepare_compiler_harness_state",
    "seed_verbatim_extracts_from_citations",
    "write_compiler_brief_scaffold",
    "refresh_compiler_claim_gaps_section",
    "refresh_compiler_verbatim_section",
]