"""Pure helper logic for entity type correction."""

from __future__ import annotations

from typing import Dict, List, Tuple

from src.ontology.schema import VALID_ENTITY_TYPES


ALLOWED_TYPES = list(VALID_ENTITY_TYPES)

FORBIDDEN_TYPES = [
    "UNKNOWN",
    "other",
    "process",
    "table",
    "image",
    "plan",
    "policy",
    "standard",
    "instruction",
    "system",
    "regulation",
    "framework",
    "objective",
    "methodology",
    "approach",
    "strategy",
    "model",
]


def identify_forbidden_entities(entities: List[Dict], *, logger=None) -> List[Dict]:
    """Scan entities, fix `#type` corruption, collect forbidden types."""
    forbidden = []
    fixed_corruption = 0

    for entity in entities:
        entity_type = entity.get("entity_type", "UNKNOWN")

        if entity_type and isinstance(entity_type, str) and entity_type.startswith("#"):
            clean_type = entity_type[1:]
            entity["entity_type"] = clean_type
            entity_type = clean_type
            fixed_corruption += 1
            if logger is not None:
                logger.debug(
                    f"Fixed corruption: {entity.get('entity_name')} - #{clean_type} → {clean_type}"
                )

        if not entity_type or entity_type == "":
            entity["entity_type"] = "UNKNOWN"
            entity_type = "UNKNOWN"

        if entity_type in FORBIDDEN_TYPES:
            forbidden.append(entity)

    if logger is not None and fixed_corruption > 0:
        logger.info(f"  ✅ Fixed {fixed_corruption} corrupted types (removed # prefix)")
        logger.info(
            f"  Found {len(forbidden)} entities with forbidden types (out of {len(entities)} total)"
        )
    return forbidden


def create_retyping_prompt(entities_batch: List[Dict]) -> str:
    """Create focused entity retyping prompt for one batch."""
    allowed_types_str = ", ".join(ALLOWED_TYPES)

    prompt = f"""You are an entity type classifier for government contracting documents.

TASK: Retype these entities using ONLY the allowed entity types below.

ALLOWED ENTITY TYPES (use EXACTLY these, lowercase with underscores):
{allowed_types_str}

FORBIDDEN TYPES (NEVER use these):
UNKNOWN, other, process, table, image, plan, policy, standard, instruction, system, regulation, framework, objective, methodology, approach, strategy, model

TYPING GUIDELINES:
- concept: Abstract ideas, business concepts, accounts, codes, processes
- document: Plans, policies, standards, regulations, manuals, reports
- deliverable: Contract deliverables with reference numbers (CDRLs, DIDs)
- technology: Systems, software, platforms, tools
- equipment: Physical assets, hardware, model numbers
- organization: Companies, agencies, departments, military units
- location: Bases, facilities, geographic locations
- requirement: Must/should/may obligations from RFP
- clause: FAR/DFARS/agency supplement clauses
- document_section: Numbered or titled structural sections, paragraphs, appendices
- program: Government programs (e.g., MCPP II)
- contract_vehicle: IDIQ/BPA/GWAC/MAC ordering frameworks
- event: Milestones, deadlines, reviews
- evaluation_factor: Section M scoring criteria (factor/subfactor/element levels)
- proposal_instruction: Proposal instructions (page limits, format, submission)
- strategic_theme: High-level themes, objectives
- work_scope_item: SOW/PWS/SOO tasks, objectives, work packages
- performance_standard: QASP thresholds, AQLs, error rates, inspection criteria
- period_of_performance: Base/option periods and ordering window structure

ENTITIES TO RETYPE:
"""

    for index, entity in enumerate(entities_batch, 1):
        name = entity.get("entity_name", "Unknown")
        desc = entity.get("description", "No description")[:150]
        current_type = entity.get("entity_type", "UNKNOWN")
        prompt += f"\n{index}. Name: {name}\n   Description: {desc}\n   Current type: {current_type}\n"

    prompt += """
OUTPUT FORMAT (one line per entity, NO explanations):
1. <entity_type>
2. <entity_type>
...

Use ONLY lowercase entity types with underscores. NO other text.
"""
    return prompt


def count_types(retyping_map: Dict[str, str]) -> Dict[str, int]:
    """Count distribution of new types after retyping."""
    counts = {}
    for new_type in retyping_map.values():
        counts[new_type] = counts.get(new_type, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def validate_no_forbidden_types(entities: List[Dict]) -> Tuple[bool, List[str]]:
    """Validate that no forbidden types remain after cleanup."""
    violations = []
    for entity in entities:
        entity_type = entity.get("entity_type", "UNKNOWN")
        if entity_type in FORBIDDEN_TYPES:
            entity_name = entity.get("entity_name", "Unknown")
            violations.append(f"{entity_name} ({entity_type})")
    return len(violations) == 0, violations