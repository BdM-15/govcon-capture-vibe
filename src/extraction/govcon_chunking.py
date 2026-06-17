"""
GovCon document classification + banner injection at chunk time.

NON-INVASIVE FOR CONTENT: Wraps LightRAG's native ``chunking_by_token_size``
and installs an idempotent native-pipeline chunk builder wrapper. No external
integration package
internals are touched.

For legacy/non-explicit chunking this is registered as LightRAG's
``chunking_func``. For explicit native strategies (``F/R/V/P``) that bypass
``chunking_func``, ``install_govcon_native_chunk_guardrails`` wraps LightRAG's
chunk dictionary builder so the same classifier-decorated chunks are persisted.

How it works
------------
1. LightRAG hands us the full post-parse content (MinerU output for PDFs,
   raw text for .txt/.md, normalized text for .docx/.xlsx) for each document.
2. We classify the document by inspecting filename echoes, section headers,
   and structural signals (e.g., repeating ``$0.00`` placeholder rows).
3. We call the native ``chunking_by_token_size`` to produce token-bounded
   chunks — identical behavior to the default path.
4. We prepend a single-line ``[GOVCON_DOC: type=...; note=...]`` banner to
   every chunk's ``content``. The banner is:

   - embedded into the chunk's vector (so retrieval surfaces template
     context whenever a template chunk is returned),
   - present in the LLM's context window during entity extraction (so the
     extractor can suppress placeholder values from becoming entities),
   - present in the LLM's context window during query response (the
     mentor prompt's Section 3a uses this to apply template guardrails).

5. We also stash ``govcon_doc_type`` on the chunk dict for any downstream
   code that wants the structured tag (LightRAG ignores unknown keys).

Doc types
---------
* ``solicitation`` — RFP, RFQ, FOPR, solicitation memorandum, UCF Sections L/M or non-UCF equivalent (FAR 16 task order, BPA call, OTA, agency-specific format)
* ``pws``          — Performance Work Statement, SOW, SOO
* ``cdrl_exhibit`` — CDRL list, Exhibit A, DD Form 1423
* ``template``     — Customer-provided fillable template (CLIN cost estimate,
  staffing matrix, Q&A submission form, past-performance reference form).
  Numeric values are offeror placeholders; structure is normative.
* ``unknown``      — Could not classify; no banner is added.
"""

from __future__ import annotations

import logging
import re
from typing import Any

try:
    from lightrag.chunker import chunking_by_token_size
except ImportError:  # pragma: no cover - compatibility with older LightRAG pins
    from lightrag.operate import chunking_by_token_size
from lightrag.utils import Tokenizer

logger = logging.getLogger(__name__)


BANNER_TEMPLATE = "[GOVCON_DOC: type={doc_type}; note={note}]"
BANNER_PREFIX = "[GOVCON_DOC:"
FOCUS_TEMPLATE = "[EXTRACT_FOCUS: {focus}]"
FOCUS_PREFIX = "[EXTRACT_FOCUS:"

_FOCUS_BY_DOC_TYPE: dict[str, str] = {
    "solicitation": (
        "Prioritize proposal_instruction, evaluation_factor, proposal_volume, and "
        "document_section hierarchy. When section headings appear, emit document_section "
        "entities and mandatory CHILD_OF edges — every evaluation_factor and "
        "proposal_instruction must attach to document_section or document in this chunk; "
        "no orphan structural nodes. Emit GUIDES when Section L instructions map to "
        "Section M factors in the same chunk. Preserve page limits, weights, and "
        "subfactor CHILD_OF chains verbatim. Never name factors from table row/cell IDs."
    ),
    "pws": (
        "Prioritize requirement, work_scope_item, workload_metric, performance_standard, "
        "deliverable, and equipment. Split action obligations from measurable thresholds "
        "(MEASURED_BY). Use CHILD_OF for section/task containment; QUANTIFIES for "
        "workload drivers."
    ),
    "cdrl_exhibit": (
        "Prioritize deliverable, requirement, document, and document_section. Preserve "
        "CDRL IDs, frequencies, distribution codes, and PWS cross-references. Link "
        "deliverables with TRACKED_BY when CDRL numbers appear."
    ),
    "template": (
        "Prioritize contract_line_item, labor_category, pricing_element, and "
        "proposal_instruction structure. Treat numeric cells as offeror placeholders — "
        "do not emit them as government workload_metric facts."
    ),
}


def render_focus_paragraph(doc_type: str) -> str:
    """Return doc-type extraction focus text for the chunk banner (not addon_params)."""
    return _FOCUS_BY_DOC_TYPE.get(doc_type, "")

# Classification rules — ordered by specificity (most specific first).
# Each rule: (doc_type, note, list of case-insensitive regex patterns).
# A rule fires if any pattern matches the first 5KB of content.
_CLASSIFICATION_RULES: list[tuple[str, str, list[str]]] = [
    (
        "template",
        (
            "Customer-provided cost/CLIN template. CLIN structure, column headers, "
            "period definitions, and FAR clause references ARE normative. Numeric "
            "values (rates, hours, totals) ARE PLACEHOLDERS the offeror replaces — "
            "do not treat them as government-asserted facts."
        ),
        [
            r"clin\s+cost\s+estimate",
            r"cost\s+schedule.*template",
            r"attachment\s+\d+\s*[-\u2013\u2014]\s*clin",
            r"attachment\s+\d+\s*[-\u2013\u2014]\s*cost",
        ],
    ),
    (
        "template",
        (
            "Customer-provided staffing matrix template. Required labor categories, "
            "skill-mix columns, and USN/LN/OCN breakdown structure ARE normative. "
            "FTE counts, hour distributions, and quantities ARE PLACEHOLDERS the "
            "offeror fills in based on the technical solution."
        ),
        [
            r"staffing\s+matrix",
            r"attachment\s+\d+\s*[-\u2013\u2014]\s*staffing",
        ],
    ),
    (
        "template",
        (
            "Customer-provided question submission template. Required format ONLY; "
            "contains no government commitments or substantive content."
        ),
        [
            r"question\s+(format|submission)\s+template",
            r"attachment\s+\d+\s*[-\u2013\u2014]\s*question",
        ],
    ),
    (
        "template",
        (
            "Customer-provided past-performance reference form. Column headers and "
            "required fields ARE normative; the form is otherwise empty for the "
            "offeror to populate with past-contract data."
        ),
        [
            r"past\s+performance\s+(reference|questionnaire)\s+(template|form)",
            r"attachment\s+\d+\s*[-\u2013\u2014]\s*past\s+performance",
            r"contractor\s+performance\s+assessment\s+report.*template",
        ],
    ),
    (
        "solicitation",
        (
            "Government solicitation document (FOPR / RFP / RFQ / solicitation "
            "memorandum). Submission instructions (proposal_instruction — UCF "
            "Section L or non-UCF equivalent, may live inline in PWS or in a "
            "named attachment) and evaluation criteria (evaluation_factor — UCF "
            "Section M or non-UCF equivalent) are authoritative. References to "
            "the PWS, CDRLs, and attachments are pointers to other documents — "
            "not the PWS content itself."
        ),
        [
            r"\bfopr\b",
            r"fair\s+opportunity\s+proposal\s+request",
            r"request\s+for\s+(proposal|quote|quotation)",
            r"memorandum\s+for\s+all\b",
            r"solicitation\s+number\s*[:#]",
            r"section\s+l\b.*instructions\s+to\s+offerors",
            r"section\s+m\b.*evaluation\s+factors",
        ],
    ),
    (
        "pws",
        (
            "Performance Work Statement — authoritative scope of work. Tasks, "
            "performance thresholds, PWS paragraph numbers, and CDRL references "
            "are binding government requirements."
        ),
        # Tighten to title-position matches only — FOPR/RFP documents reference
        # the PWS by name and would otherwise false-match this rule.
        [
            r"\battachment\s+\d+\s*[-\u2013\u2014]\s*pws\b",
            r"\A.{0,200}?performance\s+work\s+statement\s*\(pws\)",
            r"^\s*(performance\s+work\s+statement|pws)\s*$",
        ],
    ),
    (
        "cdrl_exhibit",
        (
            "CDRL Exhibit A — Contract Data Requirements List. CDRL numbers, "
            "titles, frequencies, distribution, and PWS references are binding "
            "deliverable definitions."
        ),
        [
            r"contract\s+data\s+requirements\s+list",
            r"exhibit\s+a\b.{0,40}\bcdrl\b",
            r"dd\s+form\s+1423",
        ],
    ),
]


def _has_template_structure(content_head: str) -> bool:
    """Fallback structural heuristic: many repeating placeholder cells imply template."""
    placeholder_hits = 0
    placeholder_hits += len(re.findall(r"\$\s*0\.00\b", content_head))
    placeholder_hits += len(re.findall(r"\$\s*-\s*$", content_head, re.MULTILINE))
    placeholder_hits += len(re.findall(r"\b1\s+Job\b", content_head, re.IGNORECASE))
    return placeholder_hits >= 5


def classify_document(content: str) -> tuple[str, str]:
    """Classify a document by inspecting the first 5KB of post-parse content.

    Returns ``(doc_type, note)``. Defaults to ``("unknown", "")`` when no rule
    matches and the structural-template fallback also does not fire.
    """
    head = content[:5000]
    head_lower = head.lower()

    for doc_type, note, patterns in _CLASSIFICATION_RULES:
        for pat in patterns:
            if re.search(pat, head_lower, re.IGNORECASE | re.MULTILINE):
                return doc_type, note

    # Structural fallback: many placeholder cells → template
    if _has_template_structure(head):
        return (
            "template",
            (
                "Detected by structural signal (repeating placeholder cells). "
                "Treat numeric values as offeror placeholders unless explicitly "
                "labeled as government-furnished."
            ),
        )

    return "unknown", ""


def _classification_input_from_chunks(chunks: list[dict[str, Any]]) -> str:
    ordered = sorted(
        enumerate(chunks),
        key=lambda item: (
            item[1].get("chunk_order_index")
            if isinstance(item[1].get("chunk_order_index"), int)
            else item[0]
        ),
    )
    return "\n\n".join(str(chunk.get("content") or "") for _, chunk in ordered)


def decorate_govcon_chunks(
    chunks: list[dict[str, Any]],
    *,
    source_content: str | None = None,
) -> list[dict[str, Any]]:
    """Decorate chunk dictionaries with GovCon document guardrails."""
    if not chunks:
        return chunks

    classification_content = source_content
    if classification_content is None:
        classification_content = _classification_input_from_chunks(chunks)
    doc_type, note = classify_document(classification_content)
    if doc_type == "unknown":
        return chunks

    banner = BANNER_TEMPLATE.format(doc_type=doc_type, note=note)
    focus = render_focus_paragraph(doc_type)
    focus_banner = FOCUS_TEMPLATE.format(focus=focus) if focus else ""
    for chunk in chunks:
        content = str(chunk.get("content") or "")
        if content and not content.startswith(BANNER_PREFIX):
            prefix_parts = [banner]
            if focus_banner:
                prefix_parts.append(focus_banner)
            chunk["content"] = "\n\n".join(prefix_parts + [content])
        chunk["govcon_doc_type"] = doc_type
    return chunks


def build_govcon_chunks_dict_from_chunking_result(
    chunking_result: list[dict[str, Any]],
    *,
    doc_id: str,
    file_path: str,
    base_builder: Any | None = None,
) -> dict[str, dict[str, Any]]:
    """Decorate native chunk outputs before LightRAG persists chunk dictionaries."""
    if base_builder is None:
        from lightrag.utils_pipeline import build_chunks_dict_from_chunking_result as base_builder

    decorated = decorate_govcon_chunks(list(chunking_result))
    return base_builder(decorated, doc_id=doc_id, file_path=file_path)


def _wrap_chunks_dict_builder(builder: Any) -> Any:
    if getattr(builder, "_govcon_guardrails", False):
        return builder

    def wrapped(chunking_result: list[dict[str, Any]], *, doc_id: str, file_path: str):
        return build_govcon_chunks_dict_from_chunking_result(
            chunking_result,
            doc_id=doc_id,
            file_path=file_path,
            base_builder=builder,
        )

    wrapped._govcon_guardrails = True  # type: ignore[attr-defined]
    wrapped._govcon_original = builder  # type: ignore[attr-defined]
    return wrapped


def install_govcon_native_chunk_guardrails(
    *,
    pipeline_module: Any | None = None,
    utils_pipeline_module: Any | None = None,
) -> None:
    """Patch LightRAG native chunk persistence with GovCon guardrail decoration."""
    if pipeline_module is None:
        import lightrag.pipeline as pipeline_module
    if utils_pipeline_module is None:
        import lightrag.utils_pipeline as utils_pipeline_module

    pipeline_module.build_chunks_dict_from_chunking_result = _wrap_chunks_dict_builder(
        pipeline_module.build_chunks_dict_from_chunking_result
    )
    utils_pipeline_module.build_chunks_dict_from_chunking_result = _wrap_chunks_dict_builder(
        utils_pipeline_module.build_chunks_dict_from_chunking_result
    )


def govcon_chunking_func(
    tokenizer: Tokenizer,
    content: str,
    split_by_character: str | None = None,
    split_by_character_only: bool = False,
    chunk_overlap_token_size: int = 100,
    chunk_token_size: int = 1200,
) -> list[dict[str, Any]]:
    """Drop-in replacement for ``lightrag.operate.chunking_by_token_size``.

    Signature is identical so this function can be assigned directly to
    ``global_args.chunking_func``. We delegate the actual token-aware
    splitting to LightRAG's native chunker, then decorate every chunk
    with a doc-type banner and a ``govcon_doc_type`` metadata key.
    """
    chunks = chunking_by_token_size(
        tokenizer=tokenizer,
        content=content,
        split_by_character=split_by_character,
        split_by_character_only=split_by_character_only,
        chunk_overlap_token_size=chunk_overlap_token_size,
        chunk_token_size=chunk_token_size,
    )

    decorated = decorate_govcon_chunks(chunks, source_content=content)
    doc_type = decorated[0].get("govcon_doc_type", "unknown") if decorated else "unknown"
    if doc_type != "unknown":
        logger.info(
            "GovCon chunking: %d chunks classified as '%s' (banner prepended)",
            len(decorated),
            doc_type,
        )
        return decorated

    if not decorated:
        return decorated

    logger.info(
        "GovCon chunking: %d chunks, doc_type=unknown (no banner added)",
        len(chunks),
    )
    return chunks
