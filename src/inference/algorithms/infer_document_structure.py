"""
Infer Document Structure: Heuristic Pattern Matching

CDRL/DID cross-reference detection using regex patterns.
Also detects document-section cross-references and requirement-deliverable links.
Numbered hierarchy detection (F.1.5.7 → F.1.5 → F.1).
Structural containment linking for evaluation_factor / proposal_instruction / work_scope_item.
No LLM calls - instant execution.
"""
import re
import logging
from typing import Dict, List, Set, Tuple, Optional

logger = logging.getLogger(__name__)

_STRUCTURAL_CONTAINMENT_TYPES = frozenset({
    "evaluation_factor",
    "proposal_instruction",
    "proposal_volume",
    "work_scope_item",
})


def _extract_number_prefix(name: str) -> Optional[str]:
    """
    Extract numbered prefix from entity name.

    Examples:
        "F.1.5.7 Maintenance Support" → "F.1.5.7"
        "3.2.1 Task Description" → "3.2.1"
        "Section C.5.2" → "C.5.2"
        "PWS 4.3.1 Requirements" → "4.3.1"
        "H.1.4.6 Preventive Maintenance" → "H.1.4.6"
        "Random Entity Name" → None
    """
    match = re.match(
        r"^(?:Section\s+|PWS\s+)?([A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)+)",
        name,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).upper()
    return None


def _get_parent_number(number: str) -> Optional[str]:
    """
    Get parent number by dropping last segment.

    Examples:
        "F.1.5.7" → "F.1.5"
        "3.2.1" → "3.2"
        "F.1" → "F" (or None if we don't want single letters)
        "3" → None
    """
    parts = number.split(".")
    if len(parts) <= 1:
        return None
    return ".".join(parts[:-1])


def _section_keys_from_text(text: str) -> List[str]:
    """Collect normalized section lookup keys from entity name or description."""
    keys: List[str] = []
    seen: Set[str] = set()

    def _add(key: str) -> None:
        normalized = key.strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            keys.append(normalized)

    for match in re.finditer(
        r"section\s+([a-z](?:\.\d+(?:\.\d+)*)?)",
        text,
        re.IGNORECASE,
    ):
        _add(match.group(1))
    for match in re.finditer(r"\b([a-z]\.\d+(?:\.\d+)*)\b", text, re.IGNORECASE):
        _add(match.group(1))
    for match in re.finditer(
        r"(?:task|pws|paragraph|para\.?)\s+(\d+(?:\.\d+)*)",
        text,
        re.IGNORECASE,
    ):
        _add(match.group(1))
    for match in re.finditer(r"\b(\d+(?:\.\d+)+)\b", text):
        _add(match.group(1))
    return keys


def _build_section_lookup(sections: List[Dict]) -> Dict[str, Dict]:
    """Map section keys (L.3.1, 3.2.1, M) to document_section entities."""
    lookup: Dict[str, Dict] = {}
    for sec in sections:
        name = sec.get("entity_name") or ""
        for key in _section_keys_from_text(name):
            lookup.setdefault(key, sec)
    return lookup


def _topic_section_match(entity_type: str, sections: List[Dict]) -> Optional[Dict]:
    """Fallback: single unambiguous section by topic when explicit keys are absent."""
    if entity_type == "evaluation_factor":
        candidates = [
            sec
            for sec in sections
            if re.search(r"evaluation\s+factor|section\s+m\b", (sec.get("entity_name") or ""), re.I)
        ]
    elif entity_type in {"proposal_instruction", "proposal_volume"}:
        candidates = [
            sec
            for sec in sections
            if re.search(r"section\s+l\b|instruction", (sec.get("entity_name") or ""), re.I)
        ]
    elif entity_type == "work_scope_item":
        candidates = [
            sec
            for sec in sections
            if re.search(r"task|pws|work\s+scope|section\s+c\b", (sec.get("entity_name") or ""), re.I)
        ]
    else:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return None


def _find_parent_factor(name: str, factors: List[Dict]) -> Optional[Dict]:
    """Link Subfactor 1.2 / Element 1.2.1 to Factor 1 by numeric prefix."""
    match = re.match(r"(?:subfactor|element)\s+(\d+)(?:\.|$)", name, re.IGNORECASE)
    if not match:
        return None
    factor_num = match.group(1)
    pattern = re.compile(rf"^factor\s+{factor_num}\b", re.IGNORECASE)
    for factor in factors:
        if pattern.search(factor.get("entity_name") or ""):
            return factor
    return None


def infer_document_structure(entities: List[Dict], entities_by_type: Dict) -> List[Dict]:
    """
    Infer Document Structure: Heuristic Pattern Matching (Cross-references + Hierarchy)

    Detects:
    - CDRL, DID, DD Form 1423 references
    - Document-section cross-references (e.g., "see Section 3.1")
    - PWS paragraph references
    - Attachment/Appendix references
    - **Numbered hierarchy** (F.1.5.7 → F.1.5 → F.1) via CHILD_OF
    - **Structural containment** for evaluation_factor / proposal_instruction / work_scope_item

    Non-async (no LLM calls).

    Returns:
        List of relationship dicts with REFERENCES and CHILD_OF edges
    """
    logger.info("  [Doc Structure] Heuristic Pattern Matching")

    heuristic_rels: List[Dict] = []
    seen_pairs: Set[Tuple[str, str]] = set()
    child_sources: Set[str] = set()

    deliverables = entities_by_type.get("deliverable", [])
    sections = entities_by_type.get("document_section", [])
    documents = entities_by_type.get("document", [])
    requirements = entities_by_type.get("requirement", [])
    factors = entities_by_type.get("evaluation_factor", [])

    patterns = {
        "cdrl": r"cdrl\s*[a-z]?\d{3,4}",
        "did": r"di-[a-z]+-\d{5}",
        "section_ref": r"(?:see\s+)?(?:section|paragraph|para\.?)\s+(\d+(?:\.\d+)*)",
        "attachment": r"(?:attachment|appendix|annex|exhibit)\s+([a-z]|\d+)",
        "pws_ref": r"pws\s+(?:section\s+)?(\d+(?:\.\d+)*)",
    }

    def add_relationship(
        source_id: str,
        target_id: str,
        rel_type: str,
        confidence: float,
        reason: str,
    ) -> None:
        pair = (source_id, target_id)
        if pair not in seen_pairs and source_id != target_id:
            seen_pairs.add(pair)
            heuristic_rels.append({
                "source_id": source_id,
                "target_id": target_id,
                "relationship_type": rel_type,
                "confidence": confidence,
                "reasoning": f"Heuristic: {reason}",
            })
            if rel_type == "CHILD_OF":
                child_sources.add(source_id)

    # NUMBERED HIERARCHY DETECTION (CHILD_OF)
    number_to_entity: Dict[str, Dict] = {}

    for entity in entities:
        name = entity.get("entity_name", "")
        prefix = _extract_number_prefix(name)
        if prefix and prefix not in number_to_entity:
            number_to_entity[prefix] = entity

    logger.info("    Found %d entities with numbered prefixes", len(number_to_entity))

    hierarchy_count = 0
    for number, entity in number_to_entity.items():
        parent_number = _get_parent_number(number)
        if parent_number and parent_number in number_to_entity:
            parent_entity = number_to_entity[parent_number]
            add_relationship(
                entity["id"],
                parent_entity["id"],
                "CHILD_OF",
                0.98,
                f"Numbered hierarchy: {number} → {parent_number}",
            )
            hierarchy_count += 1

    logger.info(
        "    Created %d CHILD_OF relationships from numbered hierarchy",
        hierarchy_count,
    )

    # STRUCTURAL CONTAINMENT (CHILD_OF to document_section / document)
    section_lookup = _build_section_lookup(sections)
    structural_count = 0

    for entity in entities:
        entity_type = entity.get("entity_type", "")
        if entity_type not in _STRUCTURAL_CONTAINMENT_TYPES:
            continue
        if entity["id"] in child_sources:
            continue

        name = entity.get("entity_name") or ""
        desc = entity.get("description") or ""
        parent_section: Optional[Dict] = None

        for key in _section_keys_from_text(f"{name} {desc}"):
            if key in section_lookup:
                parent_section = section_lookup[key]
                break

        if parent_section is None:
            parent_section = _topic_section_match(entity_type, sections)

        if parent_section is not None:
            add_relationship(
                entity["id"],
                parent_section["id"],
                "CHILD_OF",
                0.92,
                f"Structural containment: {entity_type} → section '{parent_section.get('entity_name', '')[:40]}'",
            )
            structural_count += 1
            continue

        if entity_type == "evaluation_factor":
            parent_factor = _find_parent_factor(name, factors)
            if parent_factor is not None:
                add_relationship(
                    entity["id"],
                    parent_factor["id"],
                    "CHILD_OF",
                    0.94,
                    f"Factor hierarchy: '{name[:40]}' → '{parent_factor.get('entity_name', '')[:40]}'",
                )
                structural_count += 1

    logger.info(
        "    Created %d CHILD_OF relationships from structural containment",
        structural_count,
    )

    # CROSS-REFERENCE DETECTION
    cdrl_index: Dict[str, Dict] = {}
    section_index: Dict[str, Dict] = {}
    doc_index: Dict[str, Dict] = {}

    for deliv in deliverables:
        name = (deliv.get("entity_name") or "").upper().replace(" ", "")
        desc = (deliv.get("description") or "").upper()
        cdrl_match = re.search(r"CDRL\s*([A-Z]?\d{3,4})", f"{name} {desc}")
        if cdrl_match:
            cdrl_key = f"CDRL{cdrl_match.group(1)}"
            cdrl_index[cdrl_key] = deliv

    for sec in sections:
        name = sec.get("entity_name") or ""
        sec_match = re.search(r"(\d+(?:\.\d+)+)", name)
        if sec_match:
            section_index[sec_match.group(1)] = sec
        for key in _section_keys_from_text(name):
            if key not in section_lookup:
                section_lookup[key] = sec

    for doc in documents:
        name = (doc.get("entity_name") or "").upper()
        att_match = re.search(r"(?:ATTACHMENT|APPENDIX|ANNEX)\s*([A-Z]|\d+)", name)
        if att_match:
            doc_index[f"ATTACHMENT{att_match.group(1)}"] = doc

    for entity in entities:
        desc = (entity.get("description") or "").lower()
        name = (entity.get("entity_name") or "").lower()
        content = f"{name} {desc}"
        entity_type = entity.get("entity_type", "")

        if entity_type == "deliverable":
            continue

        for match in re.finditer(patterns["cdrl"], content):
            cdrl_key = match.group().replace(" ", "").upper()
            if cdrl_key in cdrl_index:
                add_relationship(
                    entity["id"],
                    cdrl_index[cdrl_key]["id"],
                    "REFERENCES",
                    0.90,
                    f"CDRL cross-ref '{cdrl_key}'",
                )

        for match in re.finditer(patterns["did"], content):
            did_id = match.group().upper()
            for deliv in deliverables:
                if did_id in (deliv.get("description") or "").upper():
                    add_relationship(
                        entity["id"],
                        deliv["id"],
                        "REFERENCES",
                        0.90,
                        f"DID cross-ref '{did_id}'",
                    )
                    break

        for match in re.finditer(patterns["section_ref"], content, re.IGNORECASE):
            sec_num = match.group(1)
            if sec_num in section_index:
                add_relationship(
                    entity["id"],
                    section_index[sec_num]["id"],
                    "REFERENCES",
                    0.90,
                    f"Section cross-ref '{sec_num}'",
                )

        for match in re.finditer(patterns["attachment"], content, re.IGNORECASE):
            att_key = f"ATTACHMENT{match.group(1).upper()}"
            if att_key in doc_index:
                add_relationship(
                    entity["id"],
                    doc_index[att_key]["id"],
                    "REFERENCES",
                    0.90,
                    f"Attachment cross-ref '{match.group()}'",
                )

    for req in requirements:
        req_desc = (req.get("description") or "").lower()
        for deliv in deliverables:
            deliv_name = (deliv.get("entity_name") or "").lower()
            if len(deliv_name) > 10 and deliv_name in req_desc:
                add_relationship(
                    req["id"],
                    deliv["id"],
                    "REFERENCES",
                    0.85,
                    f"Requirement mentions deliverable '{deliv_name[:30]}...'",
                )

    logger.info("    → Algo 7: %d relationships total", len(heuristic_rels))
    return heuristic_rels