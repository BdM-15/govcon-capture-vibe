import asyncio
import json

import pytest

from src.skills.context import build_skill_briefing_book, retrieve_relevant_entities_for_skill
from src.skills.tools import ToolContext, ToolError, tool_kg_chunks, tool_kg_entities


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _ctx(tmp_path) -> ToolContext:
    return ToolContext(
        skill_name="test",
        skill_dir=tmp_path,
        run_dir=tmp_path,
        workspace_dir=tmp_path,
        workspace_name="demo",
    )


def test_tool_kg_entities_normalizes_limits_and_types(tmp_path) -> None:
    captured = {}

    def fake_slice(types, limit, max_chunks, max_relationships, _):
        captured["args"] = (types, limit, max_chunks, max_relationships)
        return {"ok": True}

    ctx = _ctx(tmp_path)
    ctx.slice_fn = fake_slice
    ctx.max_kg_entities_per_type = 10

    result = _run(
        tool_kg_entities(
            ctx,
            types=["req", None, "factor"],
            limit=999,
            max_chunks_per_entity=99,
            max_relationships_per_entity=99,
        )
    )

    assert result.payload == {"ok": True}
    assert captured["args"] == (["req", "factor"], 10, 5, 20)


def test_tool_kg_entities_requires_list_types(tmp_path) -> None:
    ctx = _ctx(tmp_path)
    ctx.slice_fn = lambda *args: {}

    with pytest.raises(ToolError, match="list of strings"):
        _run(tool_kg_entities(ctx, types="bad"))


def test_tool_kg_chunks_normalizes_mode_and_sets(tmp_path) -> None:
    captured = {}

    async def fake_retrieve(query, _, mode, top_k):
        captured["args"] = (query, mode, top_k)
        return {"names": {"B", "A"}, "chunk_ids": {"c2", "c1"}, "metadata": {"x": 1}}

    ctx = _ctx(tmp_path)
    ctx.retrieve_fn = fake_retrieve
    ctx.max_kg_chunks = 5

    result = _run(tool_kg_chunks(ctx, "hello", top_k=99, mode="weird"))

    assert captured["args"] == ("hello", "hybrid", 5)
    assert result.payload == {
        "matched_entity_names": ["A", "B"],
        "matched_chunk_ids": ["c1", "c2"],
        "metadata": {"x": 1},
    }


def test_tools_mode_kg_tools_read_native_ingested_evidence(tmp_path) -> None:
    (tmp_path / "vdb_entities.json").write_text(
        json.dumps(
            {
                "data": [
                    {
                        "entity_name": "Native Workload Requirement",
                        "entity_type": "requirement",
                        "description": "Native extraction entity",
                        "source_id": "chunk-native-workload",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "vdb_chunks.json").write_text(
        json.dumps(
            {
                "data": [
                    {
                        "__id__": "chunk-native-workload",
                        "file_path": "native-rfp.pdf",
                        "content": "Native workload chunk",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "vdb_relationships.json").write_text(json.dumps({"data": []}), encoding="utf-8")

    async def native_query_data(query: str, mode: str, history: list[dict], overrides: dict) -> dict:
        return {
            "status": "success",
            "data": {
                "entities": [{"entity_name": "Native Workload Requirement"}],
                "chunks": [{"chunk_id": "chunk-native-workload"}],
            },
        }

    ctx = _ctx(tmp_path)
    ctx.slice_fn = lambda types, limit, chunks, rels, names, *extra: build_skill_briefing_book(
        tmp_path,
        types,
        limit,
        chunks,
        rels,
        names,
    )
    ctx.retrieve_fn = lambda prompt, desc, mode, top_k: retrieve_relevant_entities_for_skill(
        native_query_data,
        prompt,
        desc,
        mode=mode,
        query_overrides={"top_k": top_k, "chunk_top_k": top_k, "only_need_context": True},
    )

    entities = _run(tool_kg_entities(ctx, types=["requirement"], limit=5))
    chunks = _run(tool_kg_chunks(ctx, "workload", top_k=5, mode="mix"))

    assert entities.payload["entities"]["requirement"][0]["name"] == "Native Workload Requirement"
    assert entities.payload["source_chunks"][0]["chunk_id"] == "chunk-native-workload"
    assert chunks.payload == {
        "matched_entity_names": ["native workload requirement"],
        "matched_chunk_ids": ["chunk-native-workload"],
        "metadata": {
            "mode": "mix",
            "top_k": 5,
            "chunk_top_k": 5,
            "max_total_tokens": None,
            "matched_entities": 1,
            "matched_chunks": 1,
            "used": True,
            "reason": "",
            "query_overrides": {"top_k": 5, "chunk_top_k": 5},
        },
    }
