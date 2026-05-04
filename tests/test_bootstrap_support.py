from pathlib import Path

from src.ontology.bootstrap_support import (
    marker_path_for_workspace,
    prepare_custom_kg,
    read_bootstrap_marker,
    resolve_workspace_dir,
    write_bootstrap_marker,
)


class _Rag:
    def __init__(self, working_dir=None):
        self.working_dir = working_dir


def test_workspace_resolution_and_marker_round_trip(tmp_path: Path) -> None:
    rag = _Rag(str(tmp_path / "from-rag"))

    assert resolve_workspace_dir(rag, None) == str(tmp_path / "from-rag")
    assert resolve_workspace_dir(rag, str(tmp_path / "explicit")) == str(tmp_path / "explicit")

    marker_path = marker_path_for_workspace(str(tmp_path / "workspace"), ".ontology_bootstrap")
    assert read_bootstrap_marker(marker_path) is None

    write_bootstrap_marker(marker_path, "2025-01-01T00:00:00")
    assert read_bootstrap_marker(marker_path) == "2025-01-01T00:00:00"


def test_prepare_custom_kg_adds_source_ids_and_synthetic_chunk() -> None:
    custom_kg = {
        "entities": [{"entity_name": "A"}],
        "relationships": [{"src_id": "A", "tgt_id": "B", "description": "desc"}],
        "chunks": [{"content": "chunk one"}],
    }

    prepared = prepare_custom_kg(custom_kg, source_label="govcon_domain_ontology")

    assert prepared["chunks"][0]["source_id"] == "govcon_domain_ontology"
    assert prepared["relationships"][0]["source_id"] == "govcon_domain_ontology"
    assert prepared["chunks"][-1]["file_path"] == "govcon_ontology"
    assert "evergreen domain context" in prepared["chunks"][-1]["content"]