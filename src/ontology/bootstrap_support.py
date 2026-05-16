"""Helper logic for ontology bootstrap orchestration."""

from __future__ import annotations

import os


def resolve_workspace_dir(lightrag, working_dir: str | None = None) -> str | None:
    """Resolve the ontology bootstrap workspace directory."""
    return working_dir or getattr(lightrag, "working_dir", None)


def marker_path_for_workspace(workspace_dir: str, marker_name: str) -> str:
    """Build the full bootstrap marker path for a workspace."""
    return os.path.join(workspace_dir, marker_name)


def read_bootstrap_marker(marker_path: str) -> str | None:
    """Return stored bootstrap timestamp if marker exists."""
    if not os.path.exists(marker_path):
        return None
    with open(marker_path, "r") as handle:
        return handle.read().strip()


def write_bootstrap_marker(marker_path: str, timestamp: str) -> None:
    """Persist bootstrap timestamp marker."""
    os.makedirs(os.path.dirname(marker_path), exist_ok=True)
    with open(marker_path, "w") as handle:
        handle.write(timestamp)


def prepare_custom_kg(custom_kg: dict[str, list[dict]], *, source_label: str) -> dict[str, list[dict]]:
    """Ensure chunks/relationships have source ids and add synthetic source chunk."""
    for chunk in custom_kg["chunks"]:
        if "source_id" not in chunk:
            chunk["source_id"] = source_label

    for relationship in custom_kg["relationships"]:
        if "source_id" not in relationship:
            relationship["source_id"] = source_label

    custom_kg["chunks"].append(
        {
            "content": (
                "GovCon Domain Ontology: Curated knowledge base for federal government "
                "contracting covering Shipley proposal methodology, FAR/DFARS compliance, "
                "evaluation methodology, BOE and staffing patterns, and lessons learned "
                "from 20+ years of federal contracting experience. "
                "This ontology provides evergreen domain context that enhances "
                "RFP-specific entity extraction and query intelligence."
            ),
            "source_id": source_label,
            "file_path": "govcon_ontology",
        }
    )
    return custom_kg