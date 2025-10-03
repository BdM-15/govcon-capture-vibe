"""
Government Contracting Ontology Configuration

Defines constrained entity types and relationship schemas for RFP knowledge graphs.
Builds on existing models in src/models/rfp_models.py and extends LightRAG entity
extraction with domain-specific validation.

Purpose:
- Prevent O(n²) relationship explosion through constrained schemas
- Ensure entity-type compatibility for relationships  
- Align with Shipley methodology and FINE_TUNING_ROADMAP.md

References:
- src/models/rfp_models.py: Core enums and models
- src/agents/rfp_agents.py: Relationship types
- docs/FINE_TUNING_ROADMAP.md: Entity taxonomy (lines 323-330)
- Shipley methodology: Structured RFP analysis
"""

from typing import Dict, List, Set, Tuple, Optional
from enum import Enum
import logging

# Import existing enums from our models
from src.models.rfp_models import (
    ComplianceLevel, RequirementType, ComplianceStatus, RiskLevel, RFPSectionType
)

logger = logging.getLogger(__name__)

# ============================================================================
# ENTITY TYPES (from FINE_TUNING_ROADMAP.md lines 323-330)
# ============================================================================

class EntityType(str, Enum):
    """
    Government contracting entity taxonomy
    
    Aligns with FINE_TUNING_ROADMAP.md entity classification for consistent
    extraction across LightRAG and PydanticAI agents.
    """
    ORGANIZATION = "ORGANIZATION"    # Contractors, agencies, departments
    CONCEPT = "CONCEPT"              # CLINs, requirements, technical concepts
    EVENT = "EVENT"                  # Milestones, deliveries, reviews
    TECHNOLOGY = "TECHNOLOGY"        # Systems, tools, platforms
    PERSON = "PERSON"                # POCs, contracting officers
    LOCATION = "LOCATION"            # Delivery sites, performance locations
    REQUIREMENT = "REQUIREMENT"      # Explicit must/should/may requirements
    CLAUSE = "CLAUSE"                # FAR clauses, contract provisions
    SECTION = "SECTION"              # RFP sections (A-M, J-attachments)
    DOCUMENT = "DOCUMENT"            # Referenced documents, attachments


# ============================================================================
# RELATIONSHIP TYPES (from src/agents/rfp_agents.py and SectionRelationship)
# ============================================================================

class RelationshipType(str, Enum):
    """
    Constrained relationship types for government contracting knowledge graphs
    
    Uses existing relationship types from src/models/rfp_models.SectionRelationship
    and extends with additional domain-specific relationships.
    """
    # Core relationships from SectionRelationship model
    REFERENCES = "references"        # One section mentions/cites another
    DEPENDS_ON = "depends_on"        # One section requires another for context
    EVALUATES = "evaluates"          # Section M evaluates content from other sections
    SUPPORTS = "supports"            # Attachments/clauses support main sections
    REQUIRES = "requires"            # Mandatory connections for compliance
    
    # Extended relationships for entity-level connections
    DEFINES = "defines"              # Entity defines a concept or term
    IMPLEMENTS = "implements"        # Entity implements a requirement
    VALIDATES = "validates"          # Entity validates a requirement or approach
    SPECIFIES = "specifies"          # Entity specifies details of another
    CONTAINS = "contains"            # Entity contains another (section contains requirements)
    CITES = "cites"                  # Entity cites a clause, regulation, or document
    DELIVERED_BY = "delivered_by"    # Deliverable delivered by organization
    PERFORMED_AT = "performed_at"    # Work performed at location
    RESPONSIBLE_FOR = "responsible_for"  # Person/org responsible for task
    APPLIES_TO = "applies_to"        # Clause/requirement applies to section/entity


# ============================================================================
# CONSTRAINED RELATIONSHIP SCHEMA
# ============================================================================

# Define valid (source_entity_type, relationship_type, target_entity_type) tuples
# This prevents O(n²) relationship explosion by constraining valid combinations

VALID_RELATIONSHIPS: Dict[Tuple[str, str], List[str]] = {
    # SECTION relationships (from SectionRelationship model)
    ("SECTION", "REFERENCES"): ["SECTION", "REQUIREMENT", "CLAUSE", "DOCUMENT"],
    ("SECTION", "DEPENDS_ON"): ["SECTION", "REQUIREMENT"],
    ("SECTION", "EVALUATES"): ["SECTION", "REQUIREMENT", "CONCEPT"],
    ("SECTION", "SUPPORTS"): ["SECTION", "REQUIREMENT"],
    ("SECTION", "REQUIRES"): ["REQUIREMENT", "DOCUMENT", "CLAUSE"],
    ("SECTION", "CONTAINS"): ["REQUIREMENT", "CONCEPT", "CLAUSE"],
    
    # REQUIREMENT relationships
    ("REQUIREMENT", "REFERENCES"): ["SECTION", "CLAUSE", "DOCUMENT", "REQUIREMENT"],
    ("REQUIREMENT", "DEPENDS_ON"): ["REQUIREMENT", "CONCEPT", "TECHNOLOGY"],
    ("REQUIREMENT", "REQUIRES"): ["TECHNOLOGY", "CONCEPT", "ORGANIZATION"],
    ("REQUIREMENT", "SPECIFIES"): ["CONCEPT", "TECHNOLOGY", "EVENT"],
    ("REQUIREMENT", "APPLIES_TO"): ["SECTION", "ORGANIZATION", "TECHNOLOGY"],
    
    # ORGANIZATION relationships
    ("ORGANIZATION", "IMPLEMENTS"): ["REQUIREMENT", "TECHNOLOGY"],
    ("ORGANIZATION", "RESPONSIBLE_FOR"): ["REQUIREMENT", "EVENT", "CONCEPT"],
    ("ORGANIZATION", "DELIVERS"): ["CONCEPT", "TECHNOLOGY", "DOCUMENT"],
    ("ORGANIZATION", "PERFORMED_AT"): ["LOCATION"],
    
    # CLAUSE relationships
    ("CLAUSE", "APPLIES_TO"): ["SECTION", "REQUIREMENT", "ORGANIZATION"],
    ("CLAUSE", "REFERENCES"): ["CLAUSE", "DOCUMENT", "SECTION"],
    ("CLAUSE", "REQUIRES"): ["REQUIREMENT", "CONCEPT"],
    
    # CONCEPT relationships (CLINs, technical concepts)
    ("CONCEPT", "DEFINED_BY"): ["SECTION", "REQUIREMENT", "DOCUMENT"],
    ("CONCEPT", "DEPENDS_ON"): ["CONCEPT", "TECHNOLOGY", "REQUIREMENT"],
    ("CONCEPT", "IMPLEMENTS"): ["REQUIREMENT"],
    ("CONCEPT", "SPECIFIES"): ["TECHNOLOGY", "EVENT"],
    
    # EVENT relationships (milestones, deliveries)
    ("EVENT", "REQUIRES"): ["CONCEPT", "DOCUMENT", "TECHNOLOGY"],
    ("EVENT", "DEPENDS_ON"): ["EVENT", "REQUIREMENT"],
    ("EVENT", "DELIVERED_BY"): ["ORGANIZATION"],
    ("EVENT", "PERFORMED_AT"): ["LOCATION"],
    
    # TECHNOLOGY relationships
    ("TECHNOLOGY", "IMPLEMENTS"): ["REQUIREMENT", "CONCEPT"],
    ("TECHNOLOGY", "SUPPORTS"): ["REQUIREMENT", "CONCEPT"],
    ("TECHNOLOGY", "DEPENDS_ON"): ["TECHNOLOGY", "CONCEPT"],
    
    # PERSON relationships
    ("PERSON", "RESPONSIBLE_FOR"): ["REQUIREMENT", "EVENT", "CONCEPT"],
    ("PERSON", "REPRESENTS"): ["ORGANIZATION"],
    
    # DOCUMENT relationships
    ("DOCUMENT", "REFERENCES"): ["SECTION", "REQUIREMENT", "CLAUSE", "DOCUMENT"],
    ("DOCUMENT", "SUPPORTS"): ["SECTION", "REQUIREMENT"],
    ("DOCUMENT", "DEFINES"): ["CONCEPT", "REQUIREMENT"],
    
    # LOCATION relationships
    ("LOCATION", "HOSTS"): ["EVENT", "ORGANIZATION"],
}


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def is_valid_relationship(
    source_entity_type: str,
    relationship_type: str,
    target_entity_type: str
) -> bool:
    """
    Validate if a relationship between entity types is valid per our constrained schema.
    
    Prevents O(n²) relationship explosion by enforcing domain-specific constraints
    aligned with government contracting ontology.
    
    Args:
        source_entity_type: Type of source entity (e.g., "SECTION", "REQUIREMENT")
        relationship_type: Type of relationship (e.g., "REFERENCES", "DEPENDS_ON")
        target_entity_type: Type of target entity
    
    Returns:
        bool: True if relationship is valid, False otherwise
    
    Example:
        >>> is_valid_relationship("SECTION", "REFERENCES", "REQUIREMENT")
        True
        >>> is_valid_relationship("PERSON", "CONTAINS", "SECTION")
        False
    """
    # Normalize to uppercase for comparison
    source = source_entity_type.upper()
    target = target_entity_type.upper()
    relation = relationship_type.lower()
    
    # Check if combination exists in schema
    key = (source, relation.upper())
    
    if key not in VALID_RELATIONSHIPS:
        logger.debug(f"Unknown relationship: {source} -{relation}-> {target}")
        return False
    
    valid_targets = VALID_RELATIONSHIPS[key]
    is_valid = target in valid_targets
    
    if not is_valid:
        logger.debug(
            f"Invalid relationship: {source} -{relation}-> {target}. "
            f"Valid targets: {valid_targets}"
        )
    
    return is_valid


def get_valid_relationships_for_entity(entity_type: str) -> Dict[str, List[str]]:
    """
    Get all valid relationships for a given entity type.
    
    Args:
        entity_type: Entity type to query (e.g., "SECTION", "REQUIREMENT")
    
    Returns:
        Dict mapping relationship types to valid target entity types
    
    Example:
        >>> get_valid_relationships_for_entity("SECTION")
        {
            "REFERENCES": ["SECTION", "REQUIREMENT", "CLAUSE", "DOCUMENT"],
            "DEPENDS_ON": ["SECTION", "REQUIREMENT"],
            ...
        }
    """
    entity = entity_type.upper()
    result = {}
    
    for (source, relation), targets in VALID_RELATIONSHIPS.items():
        if source == entity:
            result[relation] = targets
    
    return result


def validate_knowledge_graph_relationship(
    source_name: str,
    source_type: str,
    relationship: str,
    target_name: str,
    target_type: str
) -> Tuple[bool, Optional[str]]:
    """
    Validate a complete knowledge graph relationship with entity names and types.
    
    Provides detailed validation for LightRAG entity extraction, returning both
    validation result and helpful error message.
    
    Args:
        source_name: Name of source entity
        source_type: Type of source entity
        relationship: Relationship type
        target_name: Name of target entity
        target_type: Type of target entity
    
    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if relationship is valid
        - error_message: None if valid, otherwise descriptive error
    
    Example:
        >>> validate_knowledge_graph_relationship(
        ...     "Section L", "SECTION", "REFERENCES", "REQ-001", "REQUIREMENT"
        ... )
        (True, None)
    """
    is_valid = is_valid_relationship(source_type, relationship, target_type)
    
    if is_valid:
        return (True, None)
    
    # Generate helpful error message
    valid_rels = get_valid_relationships_for_entity(source_type)
    
    if relationship.upper() not in [r.upper() for r in valid_rels.keys()]:
        error_msg = (
            f"Invalid relationship '{relationship}' for entity type '{source_type}'. "
            f"Valid relationships: {list(valid_rels.keys())}"
        )
    else:
        valid_targets = valid_rels.get(relationship.upper(), [])
        error_msg = (
            f"Invalid target type '{target_type}' for relationship "
            f"'{source_name}' -{relationship}-> '{target_name}'. "
            f"Valid target types: {valid_targets}"
        )
    
    return (False, error_msg)


# ============================================================================
# ENTITY TYPE COMPATIBILITY
# ============================================================================

def get_compatible_entity_types(entity_type: str, relationship_type: str) -> List[str]:
    """
    Get list of compatible target entity types for given source type and relationship.
    
    Useful for LightRAG entity extraction to constrain target selection.
    
    Args:
        entity_type: Source entity type
        relationship_type: Relationship type
    
    Returns:
        List of valid target entity types
    
    Example:
        >>> get_compatible_entity_types("SECTION", "REFERENCES")
        ["SECTION", "REQUIREMENT", "CLAUSE", "DOCUMENT"]
    """
    key = (entity_type.upper(), relationship_type.upper())
    return VALID_RELATIONSHIPS.get(key, [])


# ============================================================================
# RELATIONSHIP IMPORTANCE (from src/agents/rfp_agents.py)
# ============================================================================

RELATIONSHIP_IMPORTANCE: Dict[str, str] = {
    # Critical relationships (from SectionRelationship model)
    "SECTION:L->SECTION:M": "critical",  # L↔M connections
    "SECTION:M->SECTION:L": "critical",
    "SECTION:L->REQUIREMENT": "critical",
    "SECTION:M->REQUIREMENT": "critical",
    
    # Important relationships
    "SECTION:I->CLAUSE": "important",    # Contract clauses
    "SECTION:C->REQUIREMENT": "important",  # SOW requirements
    "REQUIREMENT->CLAUSE": "important",
    "ORGANIZATION->REQUIREMENT": "important",
    
    # Informational relationships
    "SECTION:J->DOCUMENT": "informational",
    "DOCUMENT->SECTION": "informational",
}


def assess_relationship_importance(
    source_type: str,
    source_id: str,
    relationship: str,
    target_type: str,
    target_id: str
) -> str:
    """
    Assess importance level of a relationship (critical, important, informational).
    
    Used to prioritize relationship extraction and focus on high-value connections
    for proposal development.
    
    Args:
        source_type: Source entity type
        source_id: Source entity identifier (e.g., section ID)
        relationship: Relationship type
        target_type: Target entity type
        target_id: Target entity identifier
    
    Returns:
        Importance level: "critical", "important", or "informational"
    """
    # Check for specific patterns
    key = f"{source_type}:{source_id}->{target_type}:{target_id}"
    if key in RELATIONSHIP_IMPORTANCE:
        return RELATIONSHIP_IMPORTANCE[key]
    
    # Check for general patterns
    general_key = f"{source_type}->{target_type}"
    if general_key in RELATIONSHIP_IMPORTANCE:
        return RELATIONSHIP_IMPORTANCE[general_key]
    
    # L↔M relationships always critical
    if source_id == "L" and target_id == "M":
        return "critical"
    if source_id == "M" and target_id == "L":
        return "critical"
    
    # Section I (clauses) relationships important
    if source_id == "I" or target_id == "I":
        return "important"
    
    # Section C (SOW) to evaluation relationships important
    if source_id == "C" and target_id in ["B", "F", "M"]:
        return "important"
    
    # Default to informational
    return "informational"


# ============================================================================
# CONFIGURATION AND CONSTANTS
# ============================================================================

# Maximum relationships per entity to prevent explosion
MAX_RELATIONSHIPS_PER_ENTITY = 50

# Minimum confidence threshold for relationship extraction
MIN_RELATIONSHIP_CONFIDENCE = 0.6

# Entity types that commonly appear in government RFPs (for validation)
COMMON_RFP_ENTITY_TYPES = {
    EntityType.SECTION,
    EntityType.REQUIREMENT,
    EntityType.CLAUSE,
    EntityType.ORGANIZATION,
    EntityType.CONCEPT,
    EntityType.EVENT,
    EntityType.DOCUMENT,
}


# ============================================================================
# EXPORT CONFIGURATION
# ============================================================================

__all__ = [
    # Enums
    'EntityType',
    'RelationshipType',
    
    # Schema
    'VALID_RELATIONSHIPS',
    'RELATIONSHIP_IMPORTANCE',
    
    # Validation functions
    'is_valid_relationship',
    'get_valid_relationships_for_entity',
    'validate_knowledge_graph_relationship',
    'get_compatible_entity_types',
    'assess_relationship_importance',
    
    # Constants
    'MAX_RELATIONSHIPS_PER_ENTITY',
    'MIN_RELATIONSHIP_CONFIDENCE',
    'COMMON_RFP_ENTITY_TYPES',
]
