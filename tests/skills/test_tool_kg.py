import asyncio

import pytest

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