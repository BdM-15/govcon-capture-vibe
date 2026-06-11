"""Tool registry for the skill runtime.

Skills run as multi-turn tool-calling agents. The runtime exposes bounded tools
to the model:

* ``invoke_skill(name, prompt, context=None)`` - call one child skill in the
  same workspace (single-level Tier A chaining)
* ``read_file(path)`` — read a text file inside the skill folder
* ``run_script(path, stdin=None, timeout=60)`` — execute a script in the
  skill's ``scripts/`` folder under a sandboxed subprocess
* ``write_file(path, content, label=None)`` — persist an artifact to the run's
  ``artifacts/`` folder, optionally with a human-readable Studio label
* ``kg_query(cypher)`` — run a read-only Cypher query against the active
  workspace's Neo4j graph (no-op if Neo4j is not the active backend)
* ``kg_entities(types, limit, max_chunks_per_entity, max_relationships_per_entity)``
  — slice the workspace KG by entity type (Phase 1.5 bulk slice)
* ``kg_chunks(query, top_k, mode)`` — Phase 1.6 chat-grade hybrid retrieval
* ``web_search(query, limit)`` — public-web SERP discovery (SearXNG/SerpAPI)
* ``web_fetch(url, quality)`` — crawl/extract a URL (direct/Olostep/Firecrawl)
* ``web_research(queries, urls, …)`` — combined search + fetch pass
* ``web_provider_status()`` — configured external research providers

Every tool call is captured in the run transcript along with timing,
arguments, and a truncated preview of the result. Tools are designed to be
mechanical and bounded — model "thinking" stays in the assistant turns,
tools just fetch / execute / persist.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from src.skills.settings import skill_tools_runtime_limits
from src.skills.tool_filesystem import tool_read_file, tool_run_script, tool_write_file
from src.skills.tool_kg import tool_kg_chunks, tool_kg_entities, tool_kg_query
from src.skills.tool_mcp import build_mcp_tool_specs
from src.skills.tool_registry import ToolSpec, build_tool_specs
from src.skills.tool_types import ToolContext, ToolError, ToolResult


def serialize_tool_payload_for_model(
  result: ToolResult,
  *,
  char_cap: Optional[int] = None,
) -> str:
    """Serialize a tool result into the JSON string fed back to the model.

    OpenAI's chat protocol expects the ``content`` of a ``role: tool`` message
    to be a string; we use compact JSON. Long payloads are truncated with a
    sentinel so the model knows it's incomplete.
    """
    if char_cap is None:
      char_cap = skill_tools_runtime_limits().max_tool_result_chars
    try:
        text = json.dumps(result.payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        text = json.dumps({"error": f"unable to serialize payload: {exc}"})
    if len(text) > char_cap:
        text = text[:char_cap] + f'\n…[truncated at {char_cap} chars]'
    return text

