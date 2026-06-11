"""Pure helper logic for semantic post-processing."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict

from src.inference.relationship_inference_support import normalize_entity_name


logger = logging.getLogger(__name__)
_FACTOR_LIKE_PATTERN = re.compile(r"^(subfactor|factor)\s+([^:]+?)\s*:?[ \t]*(.+)$", re.IGNORECASE)


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


def _entity_metadata_lookup(
    entity_records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Index Neo4j entity snapshots by canonical name and entity_id (case-insensitive)."""
    lookup: dict[str, dict[str, Any]] = {}
    for record in entity_records:
        if not isinstance(record, dict):
            continue
        for key in (
            record.get("entity_name"),
            record.get("entity_id"),
        ):
            text = str(key or "").strip()
            if not text:
                continue
            lookup.setdefault(text.casefold(), record)
    return lookup


def sync_entity_metadata_to_vdb(
    rag_storage_path: str,
    entity_records: list[dict[str, Any]],
) -> int:
    """Mirror normalized Neo4j entity metadata back into ``vdb_entities.json``.

    LightRAG persists entity embeddings separately from Neo4j. Phase 2 type cleanup
    mutates Neo4j only, so query-time graph reads and file-based VDB reads can drift.
    This helper updates VDB metadata in-place without touching vectors.
    """
    if not rag_storage_path or not entity_records:
        return 0

    path = Path(rag_storage_path) / "vdb_entities.json"
    if not path.exists():
        return 0

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s for entity metadata sync: %s", path, exc)
        return 0

    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return 0

    entity_by_key = _entity_metadata_lookup(entity_records)
    if not entity_by_key:
        return 0

    updated = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("entity_name") or "").strip()
        current = entity_by_key.get(name.casefold()) if name else None
        if current is None:
            continue

        row_changed = False
        current_type = current.get("entity_type")
        if current_type and row.get("entity_type") != current_type:
            row["entity_type"] = current_type
            row_changed = True

        current_source = current.get("source_id")
        if current_source and row.get("source_id") != current_source:
            row["source_id"] = current_source
            row_changed = True

        current_desc = current.get("description")
        if current_desc and row.get("description") != current_desc:
            row["description"] = current_desc
            row_changed = True

        if row_changed:
            updated += 1

    if updated <= 0:
        return 0

    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write %s after entity metadata sync: %s", path, exc)
        return 0

    return updated


def sync_workspace_entity_metadata_from_neo4j(
    *,
    rag_storage_path: str,
    entity_records: list[dict[str, Any]],
) -> dict[str, int]:
    """Patch ``vdb_entities.json`` metadata from a Neo4j entity snapshot."""
    rows_total = count_vdb_entries(rag_storage_path, "vdb_entities.json") or 0
    updated = sync_entity_metadata_to_vdb(rag_storage_path, entity_records)
    return {
        "vdb_rows": rows_total,
        "neo4j_entities": len(entity_records),
        "rows_updated": updated,
    }


def apply_entity_name_updates_to_vdb(
    rag_storage_path: str,
    canonical_mapping: dict[str, str],
) -> dict[str, int]:
    """Rewrite canonicalized entity names in LightRAG entity and relationship VDB JSON."""
    if not rag_storage_path or not canonical_mapping:
        return {"entities_updated": 0, "relationships_updated": 0}

    entity_path = Path(rag_storage_path) / "vdb_entities.json"
    relationship_path = Path(rag_storage_path) / "vdb_relationships.json"
    entities_updated = 0
    relationships_updated = 0

    if entity_path.exists():
        try:
            payload = json.loads(entity_path.read_text(encoding="utf-8"))
            rows = payload.get("data") if isinstance(payload, dict) else payload
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    current = str(row.get("entity_name") or "").strip()
                    mapped = canonical_mapping.get(current)
                    if mapped and mapped != current:
                        row["entity_name"] = mapped
                        entities_updated += 1
                if entities_updated > 0:
                    entity_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not sync canonical entity names into %s: %s", entity_path, exc)

    if relationship_path.exists():
        try:
            payload = json.loads(relationship_path.read_text(encoding="utf-8"))
            rows = payload.get("data") if isinstance(payload, dict) else payload
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    src_id = str(row.get("src_id") or "").strip()
                    tgt_id = str(row.get("tgt_id") or "").strip()
                    mapped_src = canonical_mapping.get(src_id, src_id)
                    mapped_tgt = canonical_mapping.get(tgt_id, tgt_id)
                    if mapped_src != src_id:
                        row["src_id"] = mapped_src
                        relationships_updated += 1
                    if mapped_tgt != tgt_id:
                        row["tgt_id"] = mapped_tgt
                        relationships_updated += 1
                if relationships_updated > 0:
                    relationship_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not sync canonical relationship names into %s: %s", relationship_path, exc)

    return {
        "entities_updated": entities_updated,
        "relationships_updated": relationships_updated,
    }


def canonicalize_factor_like_name(name: str) -> str:
    """Normalize common Factor/Subfactor punctuation drift to one readable form."""
    value = str(name or "").strip()
    match = _FACTOR_LIKE_PATTERN.match(value)
    if not match:
        return value

    prefix = match.group(1).title()
    ordinal = " ".join(match.group(2).split())
    label = " ".join(match.group(3).split())
    if not ordinal or not label:
        return value
    return f"{prefix} {ordinal}: {label}"


def plan_entity_name_updates(
    grouped: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Plan low-risk canonical name updates for factor/subfactor punctuation drift."""
    name_updates: list[dict[str, Any]] = []
    canonical_mapping: dict[str, str] = {}

    duplicates: dict[str, list[dict[str, Any]]] = {}
    for entity in grouped.get("evaluation_factor", []):
        raw_name = str(entity.get("entity_name") or "").strip()
        if not raw_name:
            continue
        normalized = normalize_entity_name(raw_name.lower())
        duplicates.setdefault(normalized, []).append(entity)

    for entities in duplicates.values():
        if len(entities) < 2:
            continue

        canonical_name = max(
            (canonicalize_factor_like_name(str(entity.get("entity_name") or "")) for entity in entities),
            key=lambda name: (":" in name, len(name)),
        )
        if not canonical_name:
            continue

        for entity in entities:
            raw_name = str(entity.get("entity_name") or "").strip()
            entity_id = entity.get("id")
            if not raw_name or not entity_id:
                continue
            if raw_name == canonical_name:
                continue
            canonical_mapping[raw_name] = canonical_name
            name_updates.append(
                {
                    "id": entity_id,
                    "new_entity_name": canonical_name,
                    "old_entity_name": raw_name,
                }
            )

    return name_updates, canonical_mapping


def resolve_generic_relationship(rel_type: str, src_type: str, tgt_type: str) -> str:
    """Retype generic RELATED_TO edges using source/target entity types."""
    if rel_type not in GENERIC_REL_TYPES:
        return rel_type

    pair = (src_type.lower(), tgt_type.lower())
    return ENTITY_PAIR_REL_MAP.get(pair, rel_type)


def collect_relationship_retype_updates(
    relationships: list[dict],
    entity_by_id: dict[str, dict],
) -> list[dict]:
    """Plan RELATED_TO retypes using current entity types."""
    retype_updates = []
    for relationship in relationships:
        if relationship.get("type") not in GENERIC_REL_TYPES:
            continue

        src_entity = entity_by_id.get(relationship.get("source"))
        tgt_entity = entity_by_id.get(relationship.get("target"))
        if not src_entity or not tgt_entity:
            continue

        src_type = (src_entity.get("entity_type") or "").lower()
        tgt_type = (tgt_entity.get("entity_type") or "").lower()
        new_type = resolve_generic_relationship(relationship["type"], src_type, tgt_type)
        if new_type != relationship["type"]:
            retype_updates.append(
                {
                    "source_id": relationship["source"],
                    "target_id": relationship["target"],
                    "old_type": relationship["type"],
                    "new_type": new_type,
                }
            )
    return retype_updates


def build_post_processing_result(
    *,
    rag_storage_path: str,
    type_counts: dict[str, int],
    rel_counts: dict[str, int],
    entities_corrected: int,
    relationships_inferred: int,
    relationships_synced: int,
    processing_time: float,
    starting_entity_count: int,
    starting_relationship_count: int,
    vdb_sync_status: str,
) -> dict:
    """Build final success payload with authoritative post-processing counts."""
    final_entity_count = sum(type_counts.values())
    final_relationship_count = sum(rel_counts.values())
    vdb_entity_count = count_vdb_entries(rag_storage_path, "vdb_entities.json")
    vdb_relationship_count = count_vdb_entries(rag_storage_path, "vdb_relationships.json")

    return {
        "status": "success",
        "entities_corrected": entities_corrected,
        "relationships_inferred": relationships_inferred,
        "relationships_synced": relationships_synced,
        "processing_time": processing_time,
        "entity_type_counts": type_counts,
        "relationship_type_counts": rel_counts,
        "starting_entity_count": starting_entity_count,
        "starting_relationship_count": starting_relationship_count,
        "final_entity_count": final_entity_count,
        "final_relationship_count": final_relationship_count,
        "vdb_entity_count": vdb_entity_count,
        "vdb_relationship_count": vdb_relationship_count,
        "vdb_sync_status": vdb_sync_status,
    }


def plan_entity_type_updates(
    grouped: dict[str, list[dict]],
    *,
    allowed_types: list[str],
    table_type_mapper,
) -> tuple[list[dict], list[dict], int, int]:
    """Plan deterministic entity-type cleanup updates for Phase 2."""
    entity_updates = []
    unknown_entities = []
    table_mapped = 0
    hash_cleaned = 0
    allowed_type_names = {entity_type.lower() for entity_type in allowed_types}

    for entity_type, entity_group in grouped.items():
        entity_type_clean = entity_type.lower()
        has_hash_prefix = entity_type_clean.startswith("#")
        has_pipe_prefix = entity_type_clean.startswith("|") or entity_type_clean.startswith("#|")

        if entity_type_clean.startswith("#|"):
            entity_type_clean = entity_type_clean[2:]
        elif has_hash_prefix:
            entity_type_clean = entity_type_clean[1:]
        elif entity_type_clean.startswith("|"):
            entity_type_clean = entity_type_clean[1:]

        if entity_type_clean == "table":
            for entity in entity_group:
                mapped_type = table_type_mapper(entity)
                if mapped_type:
                    entity_updates.append({"id": entity["id"], "new_entity_type": mapped_type})
                    table_mapped += 1
            continue

        if (has_hash_prefix or has_pipe_prefix) and entity_type_clean in allowed_type_names:
            for entity in entity_group:
                entity_updates.append({"id": entity["id"], "new_entity_type": entity_type_clean})
                hash_cleaned += 1
            continue

        if entity_type_clean == "unknown":
            unknown_entities.extend(entity_group)

    return entity_updates, unknown_entities, table_mapped, hash_cleaned


def heuristic_table_type_mapping(entity: Dict) -> str:
    """Map generic multimodal `table` entities into govcon entity types."""
    name = (entity.get("entity_name") or "").lower()
    desc = (entity.get("description") or entity.get("content") or "").lower()
    text = f"{name} {desc}"

    # Section L tables often mention evaluation consequences in their description,
    # but they still function as proposal instructions. Prefer those signals first.
    if any(
        keyword in text
        for keyword in [
            "page limit",
            "page limits",
            "page allocation",
            "page allocations",
            "proposal structure",
            "proposal format",
            "volume structure",
            "volume ii",
            "volume iii",
            "submission",
            "sbpcd",
            "subcontracting goals",
            "instructions to offerors",
            "formatting and submission",
        ]
    ):
        return "proposal_instruction"

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