"""File-backed helpers for ontology knowledge bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, cast


class KnowledgeBundle(TypedDict):
    """Serialized ontology knowledge bundle."""

    source_id: str
    file_path: str
    entities: list[dict]
    relationships: list[dict]
    chunks: list[dict]


_DATA_DIR = Path(__file__).resolve().parent / "knowledge" / "data"
_REQUIRED_BUNDLE_KEYS = ("source_id", "file_path", "entities", "relationships", "chunks")


def knowledge_bundle_path(bundle_name: str) -> Path:
    """Return the on-disk path for a knowledge bundle."""

    return _DATA_DIR / f"{bundle_name}.json"


def load_knowledge_bundle(bundle_name: str) -> KnowledgeBundle:
    """Load one file-backed ontology knowledge bundle."""

    bundle_path = knowledge_bundle_path(bundle_name)
    bundle = cast(KnowledgeBundle, json.loads(bundle_path.read_text(encoding="utf-8")))
    missing_keys = [key for key in _REQUIRED_BUNDLE_KEYS if key not in bundle]
    if missing_keys:
        raise ValueError(
            f"Knowledge bundle '{bundle_name}' is missing required keys: {', '.join(missing_keys)}"
        )
    return bundle


def load_knowledge_parts(bundle_name: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Load the `(entities, relationships, chunks)` triple for one bundle."""

    bundle = load_knowledge_bundle(bundle_name)
    return bundle["entities"], bundle["relationships"], bundle["chunks"]


def load_knowledge_exports(
    bundle_name: str,
) -> tuple[str, str, list[dict], list[dict], list[dict]]:
    """Load the public exports expected from one knowledge module."""

    bundle = load_knowledge_bundle(bundle_name)
    return (
        bundle["source_id"],
        bundle["file_path"],
        bundle["entities"],
        bundle["relationships"],
        bundle["chunks"],
    )