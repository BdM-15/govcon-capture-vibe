"""Pure support helpers for ontology schema normalization and prompt guidance."""

from __future__ import annotations


EXTRACTION_TIME_RELATIONSHIP_GROUPS = {
    "Structural": ["CHILD_OF", "AMENDS", "SUPERSEDED_BY", "REFERENCES"],
    "Evaluation & Proposal": ["GUIDES", "EVALUATED_BY", "MEASURED_BY", "EVIDENCES"],
    "Work & Deliverables": [
        "PRODUCES",
        "SATISFIED_BY",
        "TRACKED_BY",
        "SUBMITTED_TO",
        "STAFFED_BY",
        "PRICED_UNDER",
        "QUANTIFIES",
    ],
    "Authority & Governance": ["GOVERNED_BY", "CONSTRAINED_BY", "DEFINES", "APPLIES_TO"],
    "Resource & Operational": ["HAS_EQUIPMENT", "PROVIDED_BY"],
    "Strategic & Capture Intelligence": ["ADDRESSES", "RELATED_TO"],
}

INFERENCE_ONLY_RELATIONSHIP_TYPES = ["REQUIRES", "ENABLED_BY", "RESPONSIBLE_FOR"]

ROGUE_RELATIONSHIP_MAPPINGS = {
    "MEASURES": "MEASURED_BY",
    "PART_OF": "CHILD_OF",
    "BELONGS_TO": "RELATED_TO",
    "CONTAINED_IN": "RELATED_TO",
    "HAS": "CHILD_OF",
    "IS_A": "RELATED_TO",
    "TYPE_OF": "RELATED_TO",
    "MEMBER_OF": "CHILD_OF",
    "ASSOCIATED_WITH": "RELATED_TO",
    "LOCATED_AT": "RELATED_TO",
    "SPECIFIES": "DEFINES",
    "FIELD_IN": "CHILD_OF",
    "INFERRED": "RELATED_TO",
    "IMPLEMENTED_BY": "SATISFIED_BY",
    "SUBJECT_TO": "GOVERNED_BY",
    "REFERENCED_BY": "REFERENCES",
    "REQUIRES_DELIVERABLE": "REQUIRES",
    "USED_FOR": "RELATED_TO",
    "CONTAINS": "CHILD_OF",
    "ATTACHMENT_OF": "CHILD_OF",
    "HAS_SUBFACTOR": "CHILD_OF",
    "FUNDS": "PRICED_UNDER",
    "MANDATES": "GOVERNED_BY",
    "RESOLVES": "ADDRESSES",
    "SUPPORTS": "RELATED_TO",
    "COORDINATED_WITH": "RELATED_TO",
    "REPORTED_TO": "SUBMITTED_TO",
}


def render_relationship_types_guidance() -> str:
    """Render canonical relationship guidance for prompt composition."""
    lines: list[str] = [
        "VALID RELATIONSHIP TYPES",
        "Extraction-time canonical types (23):",
    ]
    for group_name, rel_types in EXTRACTION_TIME_RELATIONSHIP_GROUPS.items():
        lines.append(f"- {group_name}: {', '.join(rel_types)}")

    lines.append("Inference-only types (not emitted by the LLM):")
    lines.append(f"- {', '.join(INFERENCE_ONLY_RELATIONSHIP_TYPES)}")
    return "\n".join(lines)


def normalize_relationship_type(
    rel_type: str,
    *,
    valid_relationship_types: set[str] | frozenset[str],
    fallback: str = "RELATED_TO",
    logger=None,
) -> str:
    """Normalize raw relationship type string to canonical set."""
    normalized = rel_type.strip().upper().replace(" ", "_")
    if normalized in valid_relationship_types:
        return normalized

    if normalized in ROGUE_RELATIONSHIP_MAPPINGS:
        mapped = ROGUE_RELATIONSHIP_MAPPINGS[normalized]
        if logger is not None:
            logger.info(f"Mapped rogue relationship type '{rel_type}' → '{mapped}'")
        return mapped

    if logger is not None:
        logger.warning(
            f"⚠️ Unknown relationship type '{rel_type}' → defaulting to '{fallback}'"
        )
    return fallback