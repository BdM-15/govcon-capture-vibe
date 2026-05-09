import asyncio
import json
from pathlib import Path

from src.skills.context import (
    build_skill_briefing_book,
    retrieve_relevant_entities_for_skill,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_skill_briefing_book_filters_noise_and_loads_sources(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "vdb_entities.json",
        {
            "data": [
                {
                    "entity_name": "Req A",
                    "entity_type": "requirement",
                    "description": "Perform the work",
                    "source_id": "chunk-a<SEP>chunk-b",
                },
                {
                    "entity_name": "Concept Noise",
                    "entity_type": "concept",
                    "description": "Framework background",
                    "source_id": "chunk-noise",
                },
            ]
        },
    )
    _write_json(
        tmp_path / "vdb_chunks.json",
        {
            "data": [
                {"__id__": "chunk-a", "file_path": "rfp.pdf", "content": "A" * 2000},
                {"__id__": "chunk-b", "file_path": "rfp.pdf", "content": "B"},
                {"__id__": "chunk-noise", "file_path": "guide.pdf", "content": "noise"},
            ]
        },
    )
    _write_json(
        tmp_path / "vdb_relationships.json",
        {
            "data": [
                {
                    "src_id": "Req A",
                    "tgt_id": "Eval A",
                    "keywords": "SATISFIES",
                    "description": "Requirement maps to evaluation",
                    "source_id": "chunk-a",
                }
            ]
        },
    )

    briefing = build_skill_briefing_book(
        tmp_path,
        entity_types=None,
        max_per_type=10,
        max_chunks_per_entity=1,
        max_relationships_per_entity=2,
    )

    assert list(briefing["entities"]) == ["requirement"]
    assert briefing["entities"]["requirement"] == [
        {
            "name": "Req A",
            "description": "Perform the work",
            "source_chunks": ["chunk-a"],
        }
    ]
    assert briefing["source_chunks"] == [
        {"chunk_id": "chunk-a", "file_path": "rfp.pdf", "content": "A" * 1500}
    ]
    assert briefing["relationships"] == [
        {
            "src": "Req A",
            "type": "SATISFIES",
            "tgt": "Eval A",
            "description": "Requirement maps to evaluation",
            "source_chunk": "chunk-a",
        }
    ]


def test_build_skill_briefing_book_whitelist_can_keep_retrieved_concepts(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "vdb_entities.json",
        {
            "data": [
                {
                    "entity_name": "Shipley Color Team",
                    "entity_type": "concept",
                    "description": "Retrieved background",
                    "source_id": "chunk-concept",
                },
                {
                    "entity_name": "Other Requirement",
                    "entity_type": "requirement",
                    "description": "Not retrieved",
                    "source_id": "chunk-req",
                },
            ]
        },
    )

    briefing = build_skill_briefing_book(
        tmp_path,
        entity_types=None,
        max_per_type=10,
        relevant_entity_names={"shipley color team"},
    )

    assert briefing["entities"] == {
        "concept": [
            {
                "name": "Shipley Color Team",
                "description": "Retrieved background",
                "source_chunks": ["chunk-concept"],
            }
        ]
    }


def test_retrieve_relevant_entities_for_skill_returns_whitelist_and_metadata() -> None:
    calls = []

    async def data_func(query: str, mode: str, history: list[dict], overrides: dict) -> dict:
        calls.append((query, mode, history, overrides))
        return {
            "data": {
                "entities": [
                    {"entity_name": "Req A", "entity_type": "requirement", "description": "Primary SHALL requirement."},
                    {"entity_id": "Eval B", "type": "evaluation_factor", "summary": "Assesses staffing plan quality."},
                    {"name": "Instruction C"},
                ],
                "chunks": [
                    {"chunk_id": "chunk-a", "file_path": "rfp.pdf", "content": "Staffing approach must address surge support."},
                    {"__id__": "chunk-b", "file_path": "appendix-h.pdf", "content": "Appendix H provides workload projections."},
                ],
            }
        }

    result = asyncio.run(
        retrieve_relevant_entities_for_skill(
            data_func,
            prompt="Need compliance view",
            skill_description="Audit the solicitation",
            mode="mix",
            top_k=10,
        )
    )

    assert calls == [
        (
            "Need compliance view\n\n[Skill context: Audit the solicitation]",
            "mix",
            [],
            {"top_k": 10, "chunk_top_k": 10, "only_need_context": True},
        )
    ]
    assert result["names"] == {"req a", "eval b", "instruction c"}
    assert result["chunk_ids"] == {"chunk-a", "chunk-b"}
    assert result["entities"] == [
        {"name": "Req A", "entity_type": "requirement", "summary": "Primary SHALL requirement."},
        {"name": "Eval B", "entity_type": "evaluation_factor", "summary": "Assesses staffing plan quality."},
        {"name": "Instruction C"},
    ]
    assert result["chunks"] == [
        {"chunk_id": "chunk-a", "file_path": "rfp.pdf", "content": "Staffing approach must address surge support."},
        {"chunk_id": "chunk-b", "file_path": "appendix-h.pdf", "content": "Appendix H provides workload projections."},
    ]
    assert result["metadata"] == {
        "mode": "mix",
        "top_k": 10,
        "matched_entities": 3,
        "matched_chunks": 2,
        "used": True,
        "reason": "",
    }


def test_retrieve_relevant_entities_for_skill_off_mode_skips_data_func() -> None:
    async def data_func(query: str, mode: str, history: list[dict], overrides: dict) -> dict:
        raise AssertionError("data_func should not be called")

    result = asyncio.run(
        retrieve_relevant_entities_for_skill(
            data_func,
            prompt="anything",
            skill_description="anything",
            mode="off",
            top_k=5,
        )
    )

    assert result["names"] == set()
    assert result["chunk_ids"] == set()
    assert result["entities"] == []
    assert result["chunks"] == []
    assert result["metadata"]["reason"] == "retrieval disabled (mode=off)"
