"""Core in-process tool registry for the skill runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from src.skills.settings import skill_tools_runtime_limits
from src.skills.skill_local_tools import load_skill_tool_module
from src.skills.tool_filesystem import tool_read_file, tool_run_script, tool_write_file
from src.skills.tool_kg import tool_kg_chunks, tool_kg_entities, tool_kg_query
from src.skills.tool_skill_chain import tool_invoke_skill
from src.skills.tool_types import ToolResult
from src.skills.tool_web_research import (
    tool_web_fetch,
    tool_web_provider_status,
    tool_web_research,
    tool_web_search,
)
from src.skills.tool_workspace_artifacts import tool_read_workspace_artifact


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[ToolResult]]

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def build_tool_specs(
    *,
    skill_name: str | None = None,
    skill_dir: Path | None = None,
) -> list[ToolSpec]:
    """Return the core tool registry plus any skill-specific helpers."""
    limits = skill_tools_runtime_limits()
    specs = [
        ToolSpec(
            name="invoke_skill",
            description=(
                "Invoke another Theseus skill synchronously in the same workspace. "
                "Use this for production chains such as content skill -> renderers, "
                "competitive-intel -> proposal-generator, or proposal-generator -> "
                "huashu-design. Tier A guard: one child skill only; the child cannot "
                "invoke a third skill. Returns the child run id, response preview, "
                "warnings, and artifacts."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill slug to invoke, e.g. 'renderers' or 'proposal-generator'.",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Instruction for the child skill. Include exact artifact paths or required output format.",
                    },
                    "context": {
                        "type": "object",
                        "description": "Optional structured handoff context for the child skill.",
                    },
                },
                "required": ["name", "prompt"],
                "additionalProperties": False,
            },
            handler=tool_invoke_skill,
        ),
        ToolSpec(
            name="read_workspace_artifact",
            description=(
                "Read a Studio deliverable attached to this invoke. Only artifacts "
                "listed in input_artifacts / context_artifacts are readable. Returns "
                "text or JSON content for md/txt/json/html; notes for binary docx/xlsx/pdf."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill": {
                        "type": "string",
                        "description": "Skill slug that produced the artifact.",
                    },
                    "run_id": {
                        "type": "string",
                        "description": "Run id folder under skill_runs/<skill>/.",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Artifact filename under artifacts/.",
                    },
                },
                "required": ["skill", "run_id", "filename"],
                "additionalProperties": False,
            },
            handler=tool_read_workspace_artifact,
        ),
        ToolSpec(
            name="read_file",
            description=(
                "Read a UTF-8 text file from the skill folder. Allowed roots: "
                "SKILL.md, references/, assets/, scripts/. Use this to load "
                "schemas, prompt templates, or example payloads bundled with "
                "the skill."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Skill-relative path, e.g. 'references/methodology.md'.",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=tool_read_file,
        ),
        ToolSpec(
            name="run_script",
            description=(
                "Execute a script (.py, .sh, .mjs, .js) under the skill's "
                "scripts/ folder OR any directory declared in this skill's "
                "metadata.script_paths frontmatter (typically a sibling "
                "utility skill like ../huashu-design/scripts for HTML→PPTX/"
                "PDF rendering). Subprocess sandboxed: cwd locked to the "
                "owning skill, time-limited. Returns stdout, stderr, exit code."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Path relative to this skill's directory. Either "
                            "'scripts/<file>' for own scripts, or "
                            "'../<other_skill>/scripts/<file>' for a "
                            "cross-skill script declared in metadata.script_paths."
                        ),
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional CLI arguments appended after the script path, "
                            "e.g. ['--slides', '{artifacts}/slides', '--out', "
                            "'{artifacts}/deck.pdf']. Each entry must be a string; "
                            "capped at 32 entries. No shell expansion is performed. "
                            "Placeholders {run_dir}, {artifacts}, {skill_dir} are "
                            "substituted with absolute paths so you can reference "
                            "the run's artifacts/ folder without knowing the layout."
                        ),
                        "maxItems": 32,
                    },
                    "stdin": {
                        "type": "string",
                        "description": "Optional stdin to pipe to the script.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Max seconds before SIGKILL. Capped by the runtime.",
                        "minimum": 1,
                        "maximum": 60,
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=tool_run_script,
        ),
        ToolSpec(
            name="write_file",
            description=(
                "Persist a UTF-8 text artifact to <run_dir>/artifacts/. Use "
                "this for proposal drafts, compliance matrices, infographic "
                "HTML, or any deliverable the user should download. Path is "
                "relative to the artifacts/ root. Optionally set label to a "
                "short human-readable deliverable name for the Studio UI."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Artifact path relative to artifacts/, e.g. 'volume-1-outline.md'.",
                    },
                    "content": {"type": "string", "description": "File body."},
                    "label": {
                        "type": "string",
                        "description": "Optional short display name shown in Studio, e.g. 'Volume 1 Executive Summary Draft'.",
                    },
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            handler=tool_write_file,
        ),
        ToolSpec(
            name="kg_query",
            description=(
                "Run a read-only Cypher query against the active workspace's "
                "Neo4j graph. Mutating clauses (CREATE/MERGE/DELETE/SET) are "
                "rejected. Returns up to 100 rows. If the workspace uses "
                "NetworkXStorage instead of Neo4j, the call returns "
                "available=false and the model should use kg_entities or "
                "kg_chunks instead."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "cypher": {
                        "type": "string",
                        "description": "Read-only Cypher query (MATCH/RETURN style).",
                    },
                },
                "required": ["cypher"],
                "additionalProperties": False,
            },
            handler=tool_kg_query,
        ),
        ToolSpec(
            name="kg_entities",
            description=(
                "Slice the active workspace's knowledge graph by entity type. "
                "Returns a deterministic bucket of entities with their "
                "descriptions, source chunk IDs, and connecting relationships. "
                "Use when you know which entity types you need (e.g. "
                "['proposal_instruction', 'evaluation_factor'])."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Entity types to include. Omit to get all non-noise types.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entities per type (capped by runtime).",
                        "minimum": 1,
                        "maximum": limits.max_kg_entities_per_type,
                    },
                    "max_chunks_per_entity": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": limits.max_kg_chunks_per_entity,
                        "description": "Per-entity cap on returned source chunk IDs.",
                    },
                    "max_relationships_per_entity": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": limits.max_kg_relationships_per_entity,
                        "description": "Per-entity cap on returned KG relationships.",
                    },
                },
                "additionalProperties": False,
            },
            handler=tool_kg_entities,
        ),
        ToolSpec(
            name="kg_chunks",
            description=(
                "Run chat-grade hybrid retrieval (Phase 1.6) over the active "
                "workspace. Returns ranked entity names, chunk IDs, and "
                "verbatim source_chunks content scored against the query. Use "
                "when you don't know which entity types to ask for, or when "
                "answering a free-text user question."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language retrieval query.",
                    },
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": limits.max_kg_chunks,
                        "description": "Number of entity hits to return.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["hybrid", "local", "global", "naive", "mix"],
                        "description": "Retrieval mode (default 'hybrid').",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=tool_kg_chunks,
        ),
        ToolSpec(
            name="web_search",
            description=(
                "Search the public web for discovery. Returns titled hits with URLs, "
                "snippets, and provider provenance. Free-first order: SearXNG (if "
                "configured), then SerpAPI. Use to find pages relevant to a program, "
                "agency, method, or partner — not for solicitation facts (use kg_chunks)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "description": "Max results to return (default 5).",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=tool_web_search,
        ),
        ToolSpec(
            name="web_fetch",
            description=(
                "Fetch and extract readable content from a URL. Provider fallback: "
                "direct HTTP → crawl4ai (if installed) → Olostep → Firecrawl (only "
                "when WEB_RESEARCH_ENABLE_FIRECRAWL=true or quality='premium'). "
                "Returns markdown/text with provenance. Tag external claims separately "
                "from solicitation [chunk-…] citations."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Absolute http(s) URL to fetch.",
                    },
                    "quality": {
                        "type": "string",
                        "enum": ["standard", "premium"],
                        "description": (
                            "standard = cost-conscious fallback chain; premium = prefer "
                            "Firecrawl when FIRECRAWL_API_KEY is set."
                        ),
                    },
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            handler=tool_web_fetch,
        ),
        ToolSpec(
            name="web_research",
            description=(
                "Combined external research: run search queries, fetch explicit URLs, "
                "and optionally fetch top search hits. Inputs may come from user context "
                "or prior kg_chunks/aquery seeds. Use web_provider_status first when "
                "unsure which providers are configured."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional search queries to run.",
                    },
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional explicit URLs to fetch (user-supplied or from prior analysis).",
                    },
                    "fetch_quality": {
                        "type": "string",
                        "enum": ["standard", "premium"],
                        "description": "Fetch chain quality (see web_fetch).",
                    },
                    "max_fetches": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 10,
                        "description": "Cap on total page fetches (0 = search only).",
                    },
                },
                "additionalProperties": False,
            },
            handler=tool_web_research,
        ),
        ToolSpec(
            name="web_provider_status",
            description=(
                "Return which web search/fetch providers are configured (no secrets). "
                "Call before external research when provider availability is uncertain."
            ),
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=tool_web_provider_status,
        ),
    ]

    if skill_name == "competitive-intel" and skill_dir is not None:
        obligation_tools = load_skill_tool_module(skill_dir, "competitive_intel_tools")
        specs.append(
            ToolSpec(
                name="collect_competitive_obligation_intel",
                description=(
                    "Deterministically resolve one contract number through USAspending, "
                    "classify standalone vs parent IDIQ vs order, expand child and sibling "
                    "orders, roll up obligations, compute PTW seed metrics, and write "
                    "artifacts/competitive_intel_obligation.json. Use scope='vehicle' for "
                    "Workflow B and scope='single_award' for Workflow C instead of manually "
                    "paging lookup_piid/get_award_detail/get_transactions/get_idv_children/"
                    "get_idv_activity."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "contract_number": {
                            "type": "string",
                            "description": (
                                "Raw PIID or order number to resolve, e.g. 'N00024-24-C-0085'."
                            ),
                        },
                        "scope": {
                            "type": "string",
                            "enum": ["auto", "vehicle", "single_award"],
                            "description": (
                                "Artifact/output scope. Use 'vehicle' for full Workflow B rollups, "
                                "'single_award' for Workflow C order-only artifacts, or 'auto' to "
                                "default by resolved scenario."
                            ),
                        }
                    },
                    "required": ["contract_number"],
                    "additionalProperties": False,
                },
                handler=obligation_tools.tool_collect_competitive_obligation_intel,
            )
        )

    return specs