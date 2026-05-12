"""GovCon Domain Ontology Knowledge Package.

Seven JSON-backed bundles loaded directly here via ``load_knowledge_parts``.
To add a bundle: add one call below and expose its three symbols in ``__all__``.

Bundles: shipley, regulations, evaluation, workload, capture,
         lessons_learned, company_capabilities.

Entity types align with schema.py (catalog-driven govcon types) for seamless
merging into the LightRAG KG via govcon_kg.py / bootstrap.py.
"""

from src.ontology.knowledge_support import load_knowledge_parts

SHIPLEY_ENTITIES, SHIPLEY_RELATIONSHIPS, SHIPLEY_CHUNKS = load_knowledge_parts("shipley")
REGULATION_ENTITIES, REGULATION_RELATIONSHIPS, REGULATION_CHUNKS = load_knowledge_parts("regulations")
EVALUATION_ENTITIES, EVALUATION_RELATIONSHIPS, EVALUATION_CHUNKS = load_knowledge_parts("evaluation")
WORKLOAD_ENTITIES, WORKLOAD_RELATIONSHIPS, WORKLOAD_CHUNKS = load_knowledge_parts("workload")
CAPTURE_ENTITIES, CAPTURE_RELATIONSHIPS, CAPTURE_CHUNKS = load_knowledge_parts("capture")
LESSONS_ENTITIES, LESSONS_RELATIONSHIPS, LESSONS_CHUNKS = load_knowledge_parts("lessons_learned")
COMPANY_ENTITIES, COMPANY_RELATIONSHIPS, COMPANY_CHUNKS = load_knowledge_parts("company_capabilities")

__all__ = [
    "SHIPLEY_ENTITIES", "SHIPLEY_RELATIONSHIPS", "SHIPLEY_CHUNKS",
    "REGULATION_ENTITIES", "REGULATION_RELATIONSHIPS", "REGULATION_CHUNKS",
    "EVALUATION_ENTITIES", "EVALUATION_RELATIONSHIPS", "EVALUATION_CHUNKS",
    "WORKLOAD_ENTITIES", "WORKLOAD_RELATIONSHIPS", "WORKLOAD_CHUNKS",
    "CAPTURE_ENTITIES", "CAPTURE_RELATIONSHIPS", "CAPTURE_CHUNKS",
    "LESSONS_ENTITIES", "LESSONS_RELATIONSHIPS", "LESSONS_CHUNKS",
    "COMPANY_ENTITIES", "COMPANY_RELATIONSHIPS", "COMPANY_CHUNKS",
]
