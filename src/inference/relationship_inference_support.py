"""Pure helper logic for relationship inference."""

from __future__ import annotations

from typing import Dict, List, Tuple


DUPLICATE_PRONE_TYPES = ["section", "clause", "deliverable", "document", "evaluation_factor"]


def find_potential_duplicate_pairs(
    grouped: Dict[str, List[Dict]],
    *,
    types_to_check: List[str] | None = None,
) -> Dict[str, List[Tuple[Dict, Dict]]]:
    """Return likely duplicate pairs by entity type using cheap normalization."""
    types = types_to_check or DUPLICATE_PRONE_TYPES
    pairs_by_type: Dict[str, List[Tuple[Dict, Dict]]] = {}

    for entity_type in types:
        entities = grouped.get(entity_type, [])
        if len(entities) < 2:
            continue

        potential_duplicates: List[Tuple[Dict, Dict]] = []
        for index, entity1 in enumerate(entities):
            for entity2 in entities[index + 1 :]:
                name1 = entity1.get("entity_name", "").lower().strip()
                name2 = entity2.get("entity_name", "").lower().strip()

                norm1 = normalize_entity_name(name1)
                norm2 = normalize_entity_name(name2)

                if norm1 == norm2 or (len(norm1) > 3 and norm1 in norm2) or (len(norm2) > 3 and norm2 in norm1):
                    potential_duplicates.append((entity1, entity2))

        if potential_duplicates:
            pairs_by_type[entity_type] = potential_duplicates

    return pairs_by_type


def normalize_entity_name(name: str) -> str:
    """Remove common formatting noise when comparing entity names."""
    return (
        name.replace("section", "")
        .replace("sec", "")
        .replace(".", "")
        .replace("-", "")
        .replace(":", "")
        .replace(" ", "")
    )


def build_deduplication_prompt(batch: List[Tuple[Dict, Dict]]) -> str:
    """Build LLM prompt for duplicate verification batch."""
    prompt = """You are analyzing a government RFP knowledge graph to identify duplicate entities caused by formatting variations.

TASK: Determine which entity pairs are duplicates (same concept, different formatting).

ENTITY PAIRS TO EVALUATE:
"""
    for index, (entity1, entity2) in enumerate(batch, 1):
        prompt += f"""
Pair {index}:
  Entity A: \"{entity1.get('entity_name')}\" (type: {entity1.get('entity_type')})
    Description: {entity1.get('description', '')[:150]}...
  Entity B: \"{entity2.get('entity_name')}\" (type: {entity2.get('entity_type')})
    Description: {entity2.get('description', '')[:150]}...
"""

    prompt += """
RULES FOR IDENTIFYING DUPLICATES:
1. Case variations: "SECTION C.4" == "Section C.4" == "section c.4"
2. Punctuation: "Section C.4" == "Section C-4" == "Section C4"
3. Prefix/suffix variations: "FAR 52.212-1" == "FAR clause 52.212-1"
4. Semantic equivalence: "Cost Proposal" == "Price Proposal" (if descriptions match)

OUTPUT FORMAT (JSON):
{
  "duplicates": [
    {
      "canonical_name": "Section C.4 - Supply",
      "duplicates": ["section c.4", "SECTION C.4"],
      "reasoning": "Same section with case/punctuation variations"
    }
  ]
}

Only include pairs that are TRUE duplicates. If no duplicates found, return: {"duplicates": []}
"""
    return prompt


def apply_canonical_mapping(
    nodes: List[Dict],
    edges: List[Dict],
    canonical_mapping: Dict[str, str],
) -> Tuple[List[Dict], List[Dict]]:
    """Merge duplicate nodes and rewrite edges to canonical names."""
    canonical_entities = {}
    for entity in nodes:
        name = entity.get("entity_name")
        if name in canonical_mapping:
            canonical_name = canonical_mapping[name]
            if canonical_name not in canonical_entities:
                canonical_entities[canonical_name] = {
                    "id": entity.get("id"),
                    "entity_name": canonical_name,
                    "entity_type": entity.get("entity_type"),
                    "description": entity.get("description", ""),
                    "source_id": entity.get("source_id", ""),
                }
        else:
            canonical_entities[name] = entity

    updated_edges = []
    for edge in edges:
        updated_edge = edge.copy()
        updated_edge["source"] = canonical_mapping.get(edge.get("source"), edge.get("source"))
        updated_edge["target"] = canonical_mapping.get(edge.get("target"), edge.get("target"))
        updated_edges.append(updated_edge)

    return list(canonical_entities.values()), updated_edges


def find_entity_id(entity_name: str, entities: List[Dict]) -> str | None:
    """Find entity id by exact entity name."""
    for entity in entities:
        if entity.get("entity_name") == entity_name:
            return entity.get("id")
    return None


def collect_existing_pairs(existing_edges: List[Dict]) -> set[tuple[str, str]]:
    """Collect bidirectional edge pairs for deduping inferred relationships."""
    existing_pairs: set[tuple[str, str]] = set()
    for edge in existing_edges:
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            existing_pairs.add((source, target))
            existing_pairs.add((target, source))
    return existing_pairs


def find_section_by_pattern(grouped: Dict[str, List[Dict]], section_name_pattern: str) -> Dict | None:
    """Find section entity by case-insensitive name pattern."""
    for section in grouped.get("section", []):
        name = section.get("entity_name", "").lower()
        if section_name_pattern.lower() in name:
            return section
    return None


def apply_type_based_heuristics(
    grouped: Dict[str, List[Dict]],
    existing_edges: List[Dict],
) -> List[Dict]:
    """Apply deterministic UCF relationship rules."""
    new_relationships = []
    existing_pairs = collect_existing_pairs(existing_edges)

    section_j = find_section_by_pattern(grouped, "section j")
    if section_j and "deliverable" in grouped:
        for deliverable in grouped["deliverable"]:
            source_id = deliverable.get("id")
            target_id = section_j.get("id")
            if source_id and target_id and (source_id, target_id) not in existing_pairs:
                new_relationships.append(
                    {
                        "source_id": source_id,
                        "target_id": target_id,
                        "relationship_type": "CHILD_OF",
                        "confidence": 0.90,
                        "reasoning": "Deliverables are typically listed in Section J attachments per UCF standard",
                    }
                )

    section_i = find_section_by_pattern(grouped, "section i")
    if section_i and "clause" in grouped:
        for clause in grouped["clause"]:
            source_id = clause.get("id")
            target_id = section_i.get("id")
            if source_id and target_id and (source_id, target_id) not in existing_pairs:
                new_relationships.append(
                    {
                        "source_id": source_id,
                        "target_id": target_id,
                        "relationship_type": "CHILD_OF",
                        "confidence": 0.95,
                        "reasoning": "FAR/DFARS clauses are incorporated in Section I per UCF standard",
                    }
                )

    section_m = find_section_by_pattern(grouped, "section m")
    if section_m and "evaluation_factor" in grouped:
        for factor in grouped["evaluation_factor"]:
            source_id = factor.get("id")
            target_id = section_m.get("id")
            if source_id and target_id and (source_id, target_id) not in existing_pairs:
                new_relationships.append(
                    {
                        "source_id": source_id,
                        "target_id": target_id,
                        "relationship_type": "CHILD_OF",
                        "confidence": 0.95,
                        "reasoning": "Evaluation factors are defined in Section M per UCF standard",
                    }
                )

    section_l = find_section_by_pattern(grouped, "section l")
    if section_l and "submission_instruction" in grouped:
        for instruction in grouped["submission_instruction"]:
            source_id = instruction.get("id")
            target_id = section_l.get("id")
            if source_id and target_id and (source_id, target_id) not in existing_pairs:
                new_relationships.append(
                    {
                        "source_id": source_id,
                        "target_id": target_id,
                        "relationship_type": "CHILD_OF",
                        "confidence": 0.95,
                        "reasoning": "Submission instructions are provided in Section L per UCF standard",
                    }
                )

    section_c = find_section_by_pattern(grouped, "section c")
    if section_c and "statement_of_work" in grouped:
        for sow in grouped["statement_of_work"]:
            name = sow.get("entity_name", "").lower()
            if "j-" in name or "attachment" in name or "annex" in name:
                target_section = find_section_by_pattern(grouped, "section j") or section_c
            else:
                target_section = section_c

            if target_section:
                source_id = sow.get("id")
                target_id = target_section.get("id")
                if source_id and target_id and (source_id, target_id) not in existing_pairs:
                    new_relationships.append(
                        {
                            "source_id": source_id,
                            "target_id": target_id,
                            "relationship_type": "CHILD_OF",
                            "confidence": 0.85,
                            "reasoning": "Statement of Work typically in Section C or Section J attachments per UCF standard",
                        }
                    )

    return new_relationships