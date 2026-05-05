"""Capture management ontology knowledge.

Content lives in ``data/capture.json`` so ontology knowledge can evolve as a
real content seam instead of a Python data blob.
"""

from src.ontology.knowledge_support import load_knowledge_exports

SOURCE_ID, FILE_PATH, ENTITIES, RELATIONSHIPS, CHUNKS = load_knowledge_exports(
    "capture"
)

__all__ = [
    "SOURCE_ID",
    "FILE_PATH",
    "ENTITIES",
    "RELATIONSHIPS",
    "CHUNKS",
]