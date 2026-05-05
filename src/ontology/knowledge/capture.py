"""Capture management ontology knowledge.

Content lives in ``data/capture.json`` so ontology knowledge can evolve as a
real content seam instead of a Python data blob.
"""

from src.ontology.knowledge_support import load_knowledge_bundle

_BUNDLE = load_knowledge_bundle("capture")

SOURCE_ID = _BUNDLE["source_id"]
FILE_PATH = _BUNDLE["file_path"]
ENTITIES = _BUNDLE["entities"]
RELATIONSHIPS = _BUNDLE["relationships"]
CHUNKS = _BUNDLE["chunks"]

__all__ = [
    "SOURCE_ID",
    "FILE_PATH",
    "ENTITIES",
    "RELATIONSHIPS",
    "CHUNKS",
]