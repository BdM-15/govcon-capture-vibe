"""Workload and pricing ontology knowledge.

Content lives in ``data/workload.json`` so ontology knowledge can evolve as a
real content seam instead of a Python data blob.
"""

from src.ontology.knowledge_support import load_knowledge_exports

SOURCE_ID, FILE_PATH, ENTITIES, RELATIONSHIPS, CHUNKS = load_knowledge_exports(
    "workload"
)

__all__ = [
    "SOURCE_ID",
    "FILE_PATH",
    "ENTITIES",
    "RELATIONSHIPS",
    "CHUNKS",
]