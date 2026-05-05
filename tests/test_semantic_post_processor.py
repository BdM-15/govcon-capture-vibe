import asyncio

from src.inference.semantic_post_processor import SemanticPostProcessingRun


class FakeNeo4jIO:
    def __init__(self) -> None:
        self.closed = False
        self.entity_updates = []
        self.relationship_updates = []
        self.created_relationships = []
        self._entities = [
            {"id": "n1", "entity_name": "Req 1", "entity_type": "requirement"},
            {"id": "n2", "entity_name": "CDRL A001", "entity_type": "deliverable"},
        ]
        self._relationships = [
            {"source": "n1", "target": "n2", "type": "RELATED_TO"},
        ]

    def get_all_entities(self):
        return list(self._entities)

    def get_all_relationships(self):
        return list(self._relationships)

    def update_entity_types(self, updates):
        self.entity_updates = list(updates)
        return len(updates)

    def retype_relationships(self, updates):
        self.relationship_updates = list(updates)
        return len(updates)

    def create_relationships(self, relationships):
        self.created_relationships = list(relationships)
        return len(relationships)

    def get_entity_count_by_type(self):
        return {"requirement": 1, "deliverable": 1}

    def get_relationship_count_by_type(self):
        return {"SATISFIED_BY": 2}

    def close(self):
        self.closed = True


async def fake_algorithm_runner(**kwargs):
    return [{"source": "n1", "target": "n2", "type": "SATISFIED_BY"}]


async def fake_sync_discoveries_to_vdb(**kwargs):
    return {"status": "success", "relationships_synced": 1}


def test_semantic_post_processing_run_tracks_timing_and_closes_io(tmp_path) -> None:
    fake_io = FakeNeo4jIO()
    run = SemanticPostProcessingRun(
        rag_storage_path=str(tmp_path),
        llm_model_name="grok-test",
        temperature=0.1,
        neo4j_io_factory=lambda: fake_io,
        algorithm_runner=fake_algorithm_runner,
        sync_discoveries_to_vdb_fn=fake_sync_discoveries_to_vdb,
    )

    result = asyncio.run(run.run())

    assert result["status"] == "success"
    assert result["processing_time"] >= 0
    assert result["relationships_inferred"] == 1
    assert result["relationships_synced"] == 1
    assert fake_io.relationship_updates == [
        {
            "source_id": "n1",
            "target_id": "n2",
            "old_type": "RELATED_TO",
            "new_type": "SATISFIED_BY",
        }
    ]
    assert fake_io.created_relationships == [
        {"source": "n1", "target": "n2", "type": "SATISFIED_BY"}
    ]
    assert fake_io.closed is True
    assert set(run.phase_times) == {
        "Phase 1 · Data Loading",
        "Phase 2 · Entity Normalization",
        "Phase 3 · Rel Normalization",
        "Phase 4 · Rel Inference",
        "Phase 5 · VDB Sync",
    }