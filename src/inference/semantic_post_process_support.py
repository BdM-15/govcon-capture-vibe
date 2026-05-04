"""Pure helper logic for semantic post-processing."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict


logger = logging.getLogger(__name__)


ENTITY_PAIR_REL_MAP = {
    ("requirement", "deliverable"): "SATISFIED_BY",
    ("deliverable", "requirement"): "SATISFIED_BY",
    ("requirement", "performance_standard"): "MEASURED_BY",
    ("performance_standard", "requirement"): "MEASURED_BY",
    ("work_scope_item", "deliverable"): "PRODUCES",
    ("deliverable", "work_scope_item"): "PRODUCES",
    ("requirement", "workload_metric"): "QUANTIFIES",
    ("workload_metric", "requirement"): "QUANTIFIES",
    ("deliverable", "contract_line_item"): "PRICED_UNDER",
    ("contract_line_item", "deliverable"): "PRICED_UNDER",
    ("requirement", "contract_line_item"): "PRICED_UNDER",
    ("contract_line_item", "requirement"): "PRICED_UNDER",
    ("deliverable", "organization"): "SUBMITTED_TO",
    ("organization", "deliverable"): "SUBMITTED_TO",
    ("requirement", "evaluation_factor"): "EVALUATED_BY",
    ("evaluation_factor", "requirement"): "EVALUATED_BY",
    ("deliverable", "evaluation_factor"): "EVALUATED_BY",
    ("evaluation_factor", "deliverable"): "EVALUATED_BY",
    ("work_scope_item", "evaluation_factor"): "EVALUATED_BY",
    ("evaluation_factor", "work_scope_item"): "EVALUATED_BY",
    ("evaluation_factor", "evaluation_factor"): "CHILD_OF",
    ("requirement", "clause"): "GOVERNED_BY",
    ("clause", "requirement"): "GOVERNED_BY",
    ("requirement", "regulatory_reference"): "GOVERNED_BY",
    ("regulatory_reference", "requirement"): "GOVERNED_BY",
    ("requirement", "labor_category"): "STAFFED_BY",
    ("labor_category", "requirement"): "STAFFED_BY",
    ("work_scope_item", "labor_category"): "STAFFED_BY",
    ("labor_category", "work_scope_item"): "STAFFED_BY",
    ("location", "equipment"): "HAS_EQUIPMENT",
    ("equipment", "location"): "HAS_EQUIPMENT",
    ("government_furnished_item", "organization"): "PROVIDED_BY",
    ("organization", "government_furnished_item"): "PROVIDED_BY",
    ("requirement", "customer_priority"): "ADDRESSES",
    ("customer_priority", "requirement"): "ADDRESSES",
    ("requirement", "pain_point"): "ADDRESSES",
    ("pain_point", "requirement"): "ADDRESSES",
}

GENERIC_REL_TYPES = {"RELATED_TO"}


def count_vdb_entries(rag_storage_path: str, filename: str) -> int | None:
    """Return current entry count in a LightRAG VDB JSON file."""
    if not rag_storage_path:
        return None

    path = Path(rag_storage_path) / filename
    if not path.exists():
        return None

    try:
        with path.open(encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s for final count reporting: %s", path, exc)
        return None

    data = payload.get("data", []) if isinstance(payload, dict) else payload
    if isinstance(data, (list, dict)):
        return len(data)
    return None


def resolve_generic_relationship(rel_type: str, src_type: str, tgt_type: str) -> str:
    """Retype generic RELATED_TO edges using source/target entity types."""
    if rel_type not in GENERIC_REL_TYPES:
        return rel_type

    pair = (src_type.lower(), tgt_type.lower())
    return ENTITY_PAIR_REL_MAP.get(pair, rel_type)


def heuristic_table_type_mapping(entity: Dict) -> str:
    """Map RAG-Anything `table` entities into govcon entity types."""
    name = (entity.get("entity_name") or "").lower()
    desc = (entity.get("description") or entity.get("content") or "").lower()
    text = f"{name} {desc}"

    if any(keyword in text for keyword in ["cdrl", "contract data", "deliverable", "dd form 1423", "data item"]):
        return "deliverable"

    if any(keyword in text for keyword in ["evaluation", "rating", "scoring", "assessment", "criteria", "factor"]):
        return "evaluation_factor"

    if any(keyword in text for keyword in ["performance", "metric", "sla", "kpi", "threshold", "standard", "qasp", "aql"]):
        return "performance_standard"

    if any(keyword in text for keyword in ["workload", "aircraft visit", "estimated monthly", "h.2.0", "j.2.0", "k.2.0", "l.2.0"]):
        return "requirement"

    if any(keyword in text for keyword in ["requirement", "shall", "must", "sow", "pws", "task", "work"]):
        return "requirement"

    if any(keyword in text for keyword in ["submission", "proposal", "volume", "page limit", "format"]):
        return "proposal_instruction"

    if any(keyword in text for keyword in ["far ", "dfars", "clause", "provision", "52.2"]):
        return "clause"

    if any(keyword in text for keyword in ["section", "paragraph", "attachment", "annex", "exhibit", "appendix"]):
        return "document_section"

    if any(keyword in text for keyword in ["organization", "contractor", "government", "agency"]):
        return "organization"
    if any(keyword in text for keyword in ["personnel", "staff", "position", "role", "labor category"]):
        return "labor_category"

    if any(keyword in text for keyword in ["gfe", "gfp", "gfi", "government furnished", "government-furnished"]):
        return "government_furnished_item"
    if any(keyword in text for keyword in ["equipment", "material", "supply", "asset"]):
        return "equipment"

    if any(keyword in text for keyword in ["schedule", "timeline", "milestone", "calendar", "date"]):
        return "concept"

    if any(keyword in text for keyword in ["price", "cost", "clin", "labor rate", "fee"]):
        return "concept"

    return "concept"