"""Human-readable source citations from workspace chunk metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.skills.context import SkillWorkspaceEvidenceStore

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_NOISE_DOCUMENT_MARKERS = (
    "shipley",
    "semantic inference",
    "lessons learned",
    "govcon regulations",
    "govcon ontology",
    "company capabilities",
    "evaluation methodology",
    "section_m",
    "relative_importance",
    "best value tradeoff",
    "past performance factor",
    "cpff loe",
)

_SECTION_HINT_RE = re.compile(
    r"(?:"
    r"PWS\s+Section\s+[A-Z0-9.]+|"
    r"Section\s+[LM]\s*(?:\([^)]+\))?|"
    r"Section\s+\d+(?:\.\d+)*|"
    r"FAR\s+Part\s+\d+|"
    r"DFARS\s+\d+(?:\.\d+)*|"
    r"CDRL\s+[A-Z0-9-]+|"
    r"QASP|"
    r"Factor\s+\d+\s+[^\n,]{0,40}"
    r")",
    re.IGNORECASE,
)

_ROW_KEYS_WITH_CHUNK_IDS = (
    "eval_crosswalk",
    "customer_pain_points",
    "current_methods",
    "innovation_opportunities",
    "importance_signals",
    "implicit_criteria",
    "win_theme_candidates",
    "verbatim_extracts",
)


def resolve_workspace_dir_from_run_dir(run_dir: Path) -> Path | None:
    """Walk parents from a skill run dir until vdb_chunks.json is found."""
    current = Path(run_dir).resolve()
    for _ in range(8):
        if (current / "vdb_chunks.json").is_file():
            return current
        if current.parent == current:
            break
        current = current.parent
    return None


def _strip_html(text: str) -> str:
    cleaned = _HTML_TAG_RE.sub(" ", text or "")
    return _WS_RE.sub(" ", cleaned).strip()


def is_solicitation_source(*, file_path: str | None, chunk_id: str) -> bool:
    """True when chunk likely comes from solicitation package, not ontology noise."""
    path = str(file_path or "").strip().lower().replace("\\", "/")
    if path.endswith((".pdf", ".docx", ".doc", ".html", ".htm")):
        return True
    if any(marker in path for marker in _NOISE_DOCUMENT_MARKERS):
        return False
    chunk = str(chunk_id or "").strip().lower()
    if chunk.startswith(("doc-", "tb-")):
        return True
    if chunk.startswith("chunk-") and not any(marker in path for marker in _NOISE_DOCUMENT_MARKERS):
        return bool(path)
    return False


def humanize_document_name(*, file_path: str | None, chunk_id: str) -> str:
    """Turn VDB file_path or chunk id into a reader-facing document label."""
    path = str(file_path or "").strip().replace("\\", "/")
    if path:
        name = Path(path).name or path
        name = name.replace("___", " — ").replace("__", " ").replace("_", " ")
        name = _WS_RE.sub(" ", name).strip()
        if name:
            return name

    chunk = str(chunk_id or "").strip()
    if chunk.startswith("doc-") and "-chunk-" in chunk:
        suffix = chunk.split("-chunk-", 1)[-1]
        return f"Solicitation package excerpt (chunk {suffix})"
    if chunk.startswith("tb-"):
        return "Solicitation table excerpt"
    if chunk.startswith("chunk-"):
        return "Solicitation excerpt"
    return chunk or "Workspace source"


def extract_section_hint(content: str) -> str:
    """Best-effort section/location label from chunk body."""
    plain = _strip_html(content)
    if not plain:
        return ""
    match = _SECTION_HINT_RE.search(plain)
    if match:
        return match.group(0).strip()
    if len(plain) <= 80:
        return plain
    return ""


def excerpt_quote(content: str, *, limit: int = 140) -> str:
    """Short verbatim quote for inline citation."""
    plain = _strip_html(content)
    if not plain:
        return ""
    sentence_end = re.search(r"[.!?]\s", plain)
    if sentence_end and sentence_end.start() <= limit:
        quote = plain[: sentence_end.end()].strip()
    else:
        quote = plain[:limit].strip()
    if len(plain) > len(quote):
        quote = quote.rstrip(".,;:") + "…"
    return quote


def build_source_citation(
    chunk_id: str,
    *,
    file_path: str | None = None,
    content: str | None = None,
) -> dict[str, str]:
    """Build one citation object from chunk metadata."""
    document = humanize_document_name(file_path=file_path, chunk_id=chunk_id)
    section = extract_section_hint(content or "")
    quote = excerpt_quote(content or "")
    if section and quote:
        label = f'{document}, {section}: "{quote}"'
    elif quote:
        label = f'{document}: "{quote}"'
    elif section:
        label = f"{document}, {section}"
    else:
        label = document
    return {
        "chunk_id": chunk_id,
        "document": document,
        "section": section,
        "quote": quote,
        "label": label,
    }


class ChunkCitationIndex:
    """Lookup chunk bodies and file paths from workspace VDB."""

    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = Path(workspace_dir)
        self._records: dict[str, dict[str, Any]] = {}
        store = SkillWorkspaceEvidenceStore(self.workspace_dir)
        for record in store._read_records("vdb_chunks.json"):  # noqa: SLF001
            chunk_id = str(record.get("__id__") or "").strip()
            if chunk_id:
                self._records[chunk_id] = record

    def lookup(self, chunk_id: str) -> dict[str, Any] | None:
        return self._records.get(str(chunk_id or "").strip())

    def citation_for(self, chunk_id: str) -> dict[str, str] | None:
        record = self.lookup(chunk_id)
        if record is None:
            return None
        return build_source_citation(
            chunk_id,
            file_path=str(record.get("file_path") or ""),
            content=str(record.get("content") or ""),
        )


def enrich_row_citations(row: dict[str, Any], index: ChunkCitationIndex) -> dict[str, Any]:
    """Attach source_citations[] derived from source_chunk_ids / cited_chunks."""
    if not isinstance(row, dict):
        return row
    enriched = dict(row)
    chunk_ids: list[str] = []
    for key in ("source_chunk_ids", "cited_chunks"):
        raw = row.get(key)
        if isinstance(raw, list):
            for item in raw:
                text = str(item or "").strip()
                if text and text not in chunk_ids:
                    chunk_ids.append(text)
    if not chunk_ids:
        return enriched

    citations: list[dict[str, str]] = []
    for chunk_id in chunk_ids:
        record = index.lookup(chunk_id)
        raw_path = str((record or {}).get("file_path") or "")
        if not is_solicitation_source(file_path=raw_path, chunk_id=chunk_id):
            continue
        built = index.citation_for(chunk_id)
        if built is None:
            built = build_source_citation(
                chunk_id,
                file_path=raw_path,
                content=str((record or {}).get("content") or ""),
            )
        citations.append(built)
    enriched["source_citations"] = citations
    return enriched


def enrich_payload_citations(payload: dict[str, Any], workspace_dir: Path) -> dict[str, Any]:
    """Walk known arrays and add source_citations to rows that cite chunks."""
    if not isinstance(payload, dict):
        return payload
    index = ChunkCitationIndex(workspace_dir)
    enriched = dict(payload)
    for key in _ROW_KEYS_WITH_CHUNK_IDS:
        rows = enriched.get(key)
        if not isinstance(rows, list):
            continue
        enriched[key] = [
            enrich_row_citations(row, index) if isinstance(row, dict) else row
            for row in rows
        ]
    return assign_reference_numbers(enriched)


def _citation_identity(citation: dict[str, Any]) -> str:
    chunk_id = str(citation.get("chunk_id") or "").strip()
    if chunk_id:
        return chunk_id
    return str(citation.get("label") or "").strip()


def assign_reference_numbers(payload: dict[str, Any]) -> dict[str, Any]:
    """Assign global ref numbers and build a deduplicated references[] bibliography."""
    if not isinstance(payload, dict):
        return payload

    enriched = dict(payload)
    registry: dict[str, int] = {}
    bibliography: list[dict[str, Any]] = []
    next_ref = 1

    def _register(citation: dict[str, Any]) -> dict[str, Any]:
        nonlocal next_ref
        entry = dict(citation)
        identity = _citation_identity(entry)
        if not identity:
            return entry
        ref = registry.get(identity)
        if ref is None:
            ref = next_ref
            next_ref += 1
            registry[identity] = ref
            bibliography.append({**entry, "ref": ref})
        entry["ref"] = ref
        return entry

    for key in _ROW_KEYS_WITH_CHUNK_IDS:
        rows = enriched.get(key)
        if not isinstance(rows, list):
            continue
        updated_rows: list[Any] = []
        for row in rows:
            if not isinstance(row, dict):
                updated_rows.append(row)
                continue
            updated = dict(row)
            citations = row.get("source_citations") or []
            if isinstance(citations, list) and citations:
                updated["source_citations"] = [
                    _register(item) if isinstance(item, dict) else item for item in citations
                ]
            updated_rows.append(updated)
        enriched[key] = updated_rows

    bibliography.sort(key=lambda item: int(item.get("ref") or 0))
    enriched["references"] = bibliography
    return enriched


def format_ref_markers(citations: list[Any], *, max_items: int = 4) -> str:
    """Compact numbered markers for narrative/table cells, e.g. [1][3]."""
    refs: list[int] = []
    for item in citations[:max_items]:
        if not isinstance(item, dict):
            continue
        ref = item.get("ref")
        if isinstance(ref, int) and ref > 0 and ref not in refs:
            refs.append(ref)
    if not refs:
        return ""
    suffix = ""
    if len(citations) > max_items:
        suffix = "+"
    return "".join(f"[{ref}]" for ref in refs) + suffix


def format_citations_for_table(citations: list[Any], *, max_items: int = 4) -> str:
    """Numbered reference markers for markdown table source cells."""
    return format_ref_markers(citations, max_items=max_items)


def format_citations_for_prose(citations: list[Any], *, max_items: int = 4) -> str:
    """Numbered reference markers for bullet lists and narrative."""
    return format_ref_markers(citations, max_items=max_items)


def format_reference_entry(citation: dict[str, Any]) -> str:
    """One bibliography line: document, section, optional quote."""
    ref = citation.get("ref")
    prefix = f"{ref}. " if isinstance(ref, int) and ref > 0 else "- "
    document = str(citation.get("document") or "Workspace source").strip()
    section = str(citation.get("section") or "").strip()
    quote = str(citation.get("quote") or "").strip()
    if section and quote:
        return f'{prefix}**{document}**, {section} — "{quote}"'
    if quote:
        return f'{prefix}**{document}** — "{quote}"'
    if section:
        return f"{prefix}**{document}**, {section}"
    return f"{prefix}**{document}**"


def format_references_section(references: list[Any]) -> str:
    """Markdown bibliography block for document footer."""
    if not references:
        return "## References\n\n_No source references recorded._"
    lines = ["## References", ""]
    for item in references:
        if isinstance(item, dict):
            lines.append(format_reference_entry(item))
    return "\n".join(lines)


def format_chunk_scratchpad_header(
    *,
    chunk_id: str,
    file_path: str | None = None,
    content: str | None = None,
) -> str:
    """Reader-friendly scratchpad header for one source excerpt."""
    citation = build_source_citation(chunk_id, file_path=file_path, content=content)
    lines = [f"#### {citation['document']}"]
    if citation.get("section"):
        lines.append(f"_Location: {citation['section']}_")
    lines.append(f"_Trace id: `{chunk_id}`_")
    if citation.get("quote"):
        lines.append(f'> "{citation["quote"]}"')
    return "\n".join(lines)


def enrich_json_file_citations(path: Path, workspace_dir: Path) -> bool:
    """Load JSON artifact, enrich citations, persist if changed."""
    if not path.is_file():
        return False
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(loaded, dict):
        return False
    enriched = enrich_payload_citations(loaded, workspace_dir)
    if enriched == loaded:
        return False
    path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True