"""Pure helpers for GovCon ontology KG consolidation."""

from __future__ import annotations

from typing import Any


def combine_knowledge_graph_parts(parts: list[tuple[list[dict], list[dict], list[dict]]]) -> dict[str, list[dict]]:
    """Merge `(entities, relationships, chunks)` parts into one custom_kg dict."""
    all_entities: list[dict] = []
    all_relationships: list[dict] = []
    all_chunks: list[dict] = []
    for entities, relationships, chunks in parts:
        all_entities.extend(entities)
        all_relationships.extend(relationships)
        all_chunks.extend(chunks)
    return {
        "entities": all_entities,
        "relationships": all_relationships,
        "chunks": all_chunks,
    }


def build_ontology_stats(parts_by_module: dict[str, tuple[list[dict], list[dict], list[dict]]]) -> dict[str, Any]:
    """Build per-module and total stats from ontology knowledge parts."""
    modules = {}
    total_entities = 0
    total_relationships = 0
    total_chunks = 0
    for module_name, (entities, relationships, chunks) in parts_by_module.items():
        modules[module_name] = {
            "entities": len(entities),
            "relationships": len(relationships),
            "chunks": len(chunks),
        }
        total_entities += len(entities)
        total_relationships += len(relationships)
        total_chunks += len(chunks)
    return {
        "modules": modules,
        "total_entities": total_entities,
        "total_relationships": total_relationships,
        "total_chunks": total_chunks,
    }


def validate_custom_kg(kg: dict[str, list[dict]]) -> tuple[bool, list[str]]:
    """Validate consolidated custom_kg structure for common issues."""
    errors: list[str] = []
    entity_names = set()

    for index, entity in enumerate(kg["entities"]):
        if not entity.get("entity_name"):
            errors.append(f"Entity {index}: missing entity_name")
        if not entity.get("entity_type"):
            errors.append(f"Entity {index}: missing entity_type")
        if not entity.get("description"):
            errors.append(f"Entity {index}: missing description")

        name = entity.get("entity_name", "")
        if name in entity_names:
            errors.append(f"Duplicate entity name: {name}")
        entity_names.add(name)

    for index, relationship in enumerate(kg["relationships"]):
        if not relationship.get("src_id"):
            errors.append(f"Relationship {index}: missing src_id")
        if not relationship.get("tgt_id"):
            errors.append(f"Relationship {index}: missing tgt_id")
        if not relationship.get("description"):
            errors.append(f"Relationship {index}: missing description")

        src = relationship.get("src_id", "")
        tgt = relationship.get("tgt_id", "")
        if src and src not in entity_names:
            errors.append(f"Relationship {index}: src_id '{src}' not found in entities")
        if tgt and tgt not in entity_names:
            errors.append(f"Relationship {index}: tgt_id '{tgt}' not found in entities")

    for index, chunk in enumerate(kg["chunks"]):
        if not chunk.get("content"):
            errors.append(f"Chunk {index}: missing content")

    return len(errors) == 0, errors