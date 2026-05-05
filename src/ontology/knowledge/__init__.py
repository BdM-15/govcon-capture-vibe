"""
GovCon Domain Ontology Knowledge Modules

Modular architecture for evergreen domain knowledge:
- Each module exports ENTITIES and RELATIONSHIPS lists
- A knowledge slice may be backed by Python constants or a file-backed bundle
- govcon_kg.py consolidates all modules into single custom_kg dict
- bootstrap.py injects consolidated KG into LightRAG via insert_custom_kg()

Module Categories:
- shipley.py: Shipley BD Lifecycle, Color Teams, Capture Tools
- regulations.py: FAR/DFARS compliance patterns
- evaluation.py: Rating methodologies, scoring approaches
- workload.py: BOE formulas, staffing ratios
- capture.py: Bid/No-Bid, Win Themes, Discriminators
- lessons_learned.py: 20+ years domain expertise
- company_capabilities.py: Company-specific service lines, platforms, past performance, discriminators

Entity types align with schema.py (catalog-driven govcon types) for seamless merging.
"""

from src.ontology.knowledge.shipley import ENTITIES as SHIPLEY_ENTITIES
from src.ontology.knowledge.shipley import RELATIONSHIPS as SHIPLEY_RELATIONSHIPS
from src.ontology.knowledge.shipley import CHUNKS as SHIPLEY_CHUNKS

from src.ontology.knowledge.regulations import ENTITIES as REGULATION_ENTITIES
from src.ontology.knowledge.regulations import RELATIONSHIPS as REGULATION_RELATIONSHIPS
from src.ontology.knowledge.regulations import CHUNKS as REGULATION_CHUNKS

from src.ontology.knowledge.evaluation import ENTITIES as EVALUATION_ENTITIES
from src.ontology.knowledge.evaluation import RELATIONSHIPS as EVALUATION_RELATIONSHIPS
from src.ontology.knowledge.evaluation import CHUNKS as EVALUATION_CHUNKS

from src.ontology.knowledge.workload import ENTITIES as WORKLOAD_ENTITIES
from src.ontology.knowledge.workload import RELATIONSHIPS as WORKLOAD_RELATIONSHIPS
from src.ontology.knowledge.workload import CHUNKS as WORKLOAD_CHUNKS

from src.ontology.knowledge.capture import ENTITIES as CAPTURE_ENTITIES
from src.ontology.knowledge.capture import RELATIONSHIPS as CAPTURE_RELATIONSHIPS
from src.ontology.knowledge.capture import CHUNKS as CAPTURE_CHUNKS

from src.ontology.knowledge.lessons_learned import ENTITIES as LESSONS_ENTITIES
from src.ontology.knowledge.lessons_learned import RELATIONSHIPS as LESSONS_RELATIONSHIPS
from src.ontology.knowledge.lessons_learned import CHUNKS as LESSONS_CHUNKS

from src.ontology.knowledge.company_capabilities import ENTITIES as COMPANY_ENTITIES
from src.ontology.knowledge.company_capabilities import RELATIONSHIPS as COMPANY_RELATIONSHIPS
from src.ontology.knowledge.company_capabilities import CHUNKS as COMPANY_CHUNKS

__all__ = [
    # Shipley
    "SHIPLEY_ENTITIES", "SHIPLEY_RELATIONSHIPS", "SHIPLEY_CHUNKS",
    # Regulations
    "REGULATION_ENTITIES", "REGULATION_RELATIONSHIPS", "REGULATION_CHUNKS",
    # Evaluation
    "EVALUATION_ENTITIES", "EVALUATION_RELATIONSHIPS", "EVALUATION_CHUNKS",
    # Workload
    "WORKLOAD_ENTITIES", "WORKLOAD_RELATIONSHIPS", "WORKLOAD_CHUNKS",
    # Capture
    "CAPTURE_ENTITIES", "CAPTURE_RELATIONSHIPS", "CAPTURE_CHUNKS",
    # Lessons Learned
    "LESSONS_ENTITIES", "LESSONS_RELATIONSHIPS", "LESSONS_CHUNKS",
    # Company Capabilities
    "COMPANY_ENTITIES", "COMPANY_RELATIONSHIPS", "COMPANY_CHUNKS",
]
